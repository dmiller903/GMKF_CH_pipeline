import glob
import gzip
import re
from sys import argv
import os
import time
import concurrent.futures

# Keep track of when the script began
startTime = time.time()
char = '\n' + ('*' * 70) + '\n'

# Input information from argv
inputFile = argv[1]
pathToFiles = argv[2]
if pathToFiles.endswith("/"):
    pathToFiles = pathToFiles[0:-1]

#Create a dictionary of trio files that need to be phased
fileDict = dict()
with open(inputFile) as sampleFile:
        header = sampleFile.readline()
        headerList = header.rstrip().split("\t")
        fileNameIndex = headerList.index("file_name")
        familyIdIndex = headerList.index("family_id")
        sampleIdIndex = headerList.index("sample_id")
        chromosomes = {"chr1", "chr2", "chr3", "chr4", "chr5", "chr6", "chr7", "chr8", "chr9", "chr10", "chr11", \
        "chr12", "chr13", "chr14", "chr15", "chr16", "chr17", "chr18", "chr19", "chr20", "chr21", "chr22"}
        for sample in sampleFile:
            sampleData = sample.rstrip("\n").split("\t")
            fileName = sampleData[fileNameIndex]
            sampleFamilyId = sampleData[familyIdIndex]
            sampleId = sampleData[sampleIdIndex]
            for chromosome in chromosomes:
                trioFileName = f"{pathToFiles}/{sampleFamilyId}/{sampleFamilyId}_trio/{sampleFamilyId}_trio_{chromosome}_phased_mcmc.vcf"
                if os.path.exists(f"{trioFileName}"):
                    if sampleFamilyId not in fileDict:
                        fileDict[sampleFamilyId] = set()
                        fileDict[sampleFamilyId].add(trioFileName)
                    else:
                        fileDict[sampleFamilyId].add(trioFileName)

#Create a position dictionary based off of the legend.gz files
posDict = dict()
for file in glob.glob("/references/1000GP_Phase3/*legend.gz"):
    with gzip.open(file, 'rt') as legend:
        chrom = re.findall(r"[\w_/]+_chr([0-9]+)\.legend\.gz", file)[0]
        header = legend.readline()
        headerList = header.rstrip().split()
        refIndex = headerList.index("a0")
        altIndex = headerList.index("a1")
        posIndex = headerList.index("position")
        idIndex = headerList.index("id")
        for line in legend:
            lineList = line.rstrip().split(" ")
            pos = lineList[posIndex]
            ref = lineList[refIndex]
            alt = lineList[altIndex]
            siteStr = f"{pos} {ref} {alt}"
            if chrom not in posDict:
                posDict[chrom] = {siteStr}
            else:
                posDict[chrom].add(siteStr)

print("Dictionary Created\n")

# Function to create new files with alt/ref flipped and remove sites with mendel errors
def altRefRevert(file):
    fileNameNoSuffix = re.findall(r"(.+_chr[A-Z0-9][A-Z0-9]?_phased_mcmc)\.vcf", file)[0]
    outputName = f"{fileNameNoSuffix}_reverted.vcf"
    # Create a set of any positions with mendel errors as given by the shapeit2 .snp.me files
    mendelErrorFile = f"{fileNameNoSuffix}.snp.me"
    mendelErrorSet = set()
    if os.path.exists(mendelErrorFile):
        with open(mendelErrorFile) as mendelFile:
            for line in mendelFile:
                lineSplit = line.split("\t")
                mendelError = lineSplit[2]
                pos = lineSplit[1]
                if mendelError == "1":
                    mendelErrorSet.add(pos)

    # Create new files with alt/ref flipped and remove sites with mendel errors 
    with open(file, 'rt') as sample, open(outputName, 'w') as output:
        rawCount = 0
        flipCount = 0
        total = 0
        mendelErrorCount = 0 
        for line in sample:
            if "##" in line:
                output.write(line)
            elif line.startswith("#CHROM"):
                header = line.split("\t")
                chromIndex = header.index("#CHROM")
                posIndex = header.index("POS")
                refIndex = header.index("REF")
                altIndex = header.index("ALT")
                output.write(line)
            else:
                lineList = line.split("\t")
                chrom = lineList[chromIndex]
                pos = lineList[posIndex]
                ref = lineList[refIndex]
                alt = lineList[altIndex]
                rawStr = f"{pos} {ref} {alt}"
                flipStr = f"{pos} {alt} {ref}"
                if rawStr in posDict[chrom] and pos not in mendelErrorSet:
                    output.write(line)
                    rawCount += 1
                    total += 1
                elif flipStr in posDict[chrom] and pos not in mendelErrorSet:
                    lineList[refIndex] = alt
                    lineList[altIndex] = ref
                    line = "\t".join(lineList)
                    line = line.replace("0|1", "b|a").replace("1|0", "a|b").replace("1|1", "a|a").replace("0|0", "b|b")
                    line = line.replace("b|a", "1|0").replace("a|b", "0|1").replace("a|a", "0|0").replace("b|b", "1|1")
                    output.write(line)
                    flipCount += 1
                    total += 1
                else:
                    total += 1
                    mendelErrorCount += 1
        rawPercent = (rawCount / total) * 100
        flipPercent = (flipCount / total) * 100
        totalPercent = ((flipCount + rawCount) / total) * 100
        print(f"For {file}, {rawCount} ({rawPercent:.2f}%) of the sites were unchanged")
        print(f"For {file}, {flipCount} ({flipPercent:.2f}%) of the sites were switched to match the reference panel")
        print(f"For {file}, {mendelErrorCount} sites were removed due to mendel errors\n")
        print(f"For {file}, {totalPercent:.2f}% of the sites were kept and are now congruent with the reference panel\n")

# Create new files with alt/ref flipped and remove sites with mendel errors using fileDict where key is familyID and value is list of files
# for members of that family. 
for trio, trioFiles in fileDict.items():
    with concurrent.futures.ProcessPoolExecutor(max_workers=23) as executor:
        executor.map(altRefRevert, trioFiles)

# Output message and time complete
timeElapsedMinutes = round((time.time()-startTime) / 60, 2)
timeElapsedHours = round(timeElapsedMinutes / 60, 2)
print(f'{char}Done. Time elapsed: {timeElapsedMinutes} minutes ({timeElapsedHours} hours){char}')