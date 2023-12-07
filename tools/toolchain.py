#!/usr/bin/python3

#####################################################################################
# Copyright (c) 2023 Randal E. Bryant, Carnegie Mellon University
# Last edit: May 20, 2023
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
# associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute,
# sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
# NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
# OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
########################################################################################

# Run model counting program on benchmark file
# Use newer versions of programs

import getopt
import sys
import os.path
import subprocess
import datetime
import time

def usage(name):
    print("Usage: %s [-h] [-v VERB] [-1] [-m] [-L] [-S] [-G] [-F] FILE.EXT ..." % name)
    print("  -h       Print this message")
    print("  -v VERB  Set verbosity level.  Level 2 causes comments in .cpog file")
    print("  -1       Generate one-sided proof (don't validate assertions)")
    print("  -m       Monolithic mode: Do validation with single call to SAT solver")
    print("  -L       Expand each node, rather than using lemmas")
    print("  -G       Prove each literal separately, rather than grouping into single proof")
    print("  -F       Run Lean checker to formally check")
    print("  -S       SSAT certification")
    print("  EXT      Can be any extension for wild-card matching (e.g., cnf, nnf)")
    

# Defaults
standardTimeLimit = 60

oneSided = False
monolithic = False
useLemma = True
group = True
useLean = False
certSSAT = False

# Pathnames
d4Home = "../tools"         # Yun-Rong Luo modified
d4Program = d4Home + "/d4"

ssatHome = "../../tools"
ssatProgram = ssatHome + "/SharpSSAT"

evalHome = "../../src"
evalProgram = evalHome + "/evalSSAT"

genHome = "../src"
genProgram = genHome + "/cpog-gen"

checkHome = "../src"
checkProgram = checkHome + "/cpog-check"

leanHome =  "../VerifiedChecker"
leanCheckProgram = leanHome + "/build/bin/checker"

timeLimits = { "D4" : 4000, "GEN" : 600, "FCHECK" : 600 , "LCHECK" : 4000, "SSAT" : 360, "EVAL" : 360 }

clauseLimit = (1 << 31) - 1

commentChar = 'c'

verbLevel = 1

def checkFile(prefix, fname, logFile):
    f = open(fname, 'r')
    bytes = 0
    lines = 0
    for line in f:
        if len(line) > 0 and line[0] == commentChar:
            continue
        bytes += len(line)
        lines += 1
    print("%s: LOG: size %s %d lines %d bytes" % (prefix, fname, lines, bytes))
    logFile.write("%s: LOG: size %s %d lines %d bytes\n" % (prefix, fname, lines, bytes))
    f.close()

def runProgram(prefix, root, commandList, logFile, extraLogName = None):
    if prefix in timeLimits:
        timeLimit = timeLimits[prefix]
    else:
        timeLimit = standardTimeLimit
    result = ""
    cstring = " ".join(commandList)
    print("%s. %s: Running '%s' with time limit of %d seconds" % (root, prefix, cstring, timeLimit))
    logFile.write("%s LOG: Running %s\n" % (prefix, cstring))
    logFile.write("%s LOG: Time limit %d seconds\n" % (prefix, timeLimit))
    start = datetime.datetime.now()
    try:
        cp = subprocess.run(commandList, capture_output = True, timeout=timeLimit, text=True)
    except subprocess.TimeoutExpired as ex:
        # Incorporate information recorded by external logging
        if (extraLogName is not None):
            try:
                xlog = open(extraLogName, "r")
                for line in xlog:
                    logFile.write(line)
                xlog.close()
            except:
                pass
        print("%s. %s Program timed out after %d seconds" % (root, prefix, timeLimit))
        result += "%s ERROR: Timeout after %d seconds\n" % (prefix, timeLimit)
        delta = datetime.datetime.now() - start
        seconds = delta.seconds + 1e-6 * delta.microseconds
        result += "%s LOG: Elapsed time = %.3f seconds\n" % (prefix, seconds)
        result += "%s OUTCOME: Timeout\n" % (prefix)
        logFile.write(result)
        return False
    ok = True
    if cp.returncode != 0:
        result += "%s ERROR: Return code = %d\n" % (prefix, cp.returncode)
        ok = False
    outcome = "normal" if ok else "failed"
    delta = datetime.datetime.now() - start
    seconds = delta.seconds + 1e-6 * delta.microseconds
    result += "%s LOG: Elapsed time = %.3f seconds\n" % (prefix, seconds)
    result += "%s OUTCOME: %s\n" % (prefix, outcome)
    print("%s. %s: OUTCOME: %s" % (root, prefix, outcome))
    print("%s. %s: Elapsed time: %.3f seconds" % (root, prefix, seconds))
    logFile.write(cp.stdout)
    logFile.write(result)
    return ok

# Only run D4 if don't yet have .nnf file
def runD4(root, home, logFile, force):
    cnfName = home + "/" + root + ".cnf"
    nnfName = home + "/" + root + ".nnf"
    if not force and os.path.exists(nnfName):
        return True
    cmd = [d4Program, cnfName, "-dDNNF", "-out=" + nnfName]
    ok = runProgram("D4", root, cmd, logFile)
    if not ok and os.path.exists(nnfName):
        os.remove(nnfName)
    return ok

def runSharpSSAT(root, home, logFile, force):
    ssatName = home + "/" + root + ".sdimacs"
    upNNFName = home + "/" + root + "_up.nnf"
    if not force and os.path.exists(upNNFName):
        return True
    lowNNFName = home + "/" + root + "_low.nnf"
    if not force and os.path.exists(lowNNFName):
        return True
    cmd = [ssatProgram, "-l", "-p", "-s", ssatName]
    ok = runProgram("SSAT", root, cmd, logFile)
    if not ok and os.path.exists(upNNFName):
        os.remove(upNNFName)
    if not ok and os.path.exists(lowNNFName):
        os.remove(lowNNFName)
    return ok

def runEvalSSAT(root, home, logFile, force):
    ssatName = home + "/" + root + ".sdimacs"
    upNNFName = home + "/" + root + "_up.nnf"
    lowNNFName = home + "/" + root + "_low.nnf"
    probName  = home + "/" + root + ".prob"
    cmd = [evalProgram, ssatName, upNNFName, lowNNFName, probName]
    ok = runProgram("EVAL", root, cmd, logFile)
    return ok

def lowBound_isOne(root, home, logFile):
    probName  = home + "/" + root + ".prob"
    probVal = []
    with open(probName) as probFile:
        for line in probFile.readlines():
            probVal.append(float(line))
    if probVal[0] == 1.0:
        logFile.write("LOWER BOUND: lower bound=1.0.  Skipped UPPER BOUND\n")
        return True 
    return False

def runPartialGen(root, home, logFile, force):
    cnfName = home + "/" + root + ".cnf"
    nnfName = home + "/" + root + ".nnf"
    cpogName = home + "/" + root + ".cpog"
    cmd = [genProgram, "-p", cnfName, nnfName, cpogName]
    ok = runProgram("GEN", root, cmd, logFile)
    if not ok and os.path.exists(cpogName):
        os.remove(cpogName)
    return ok


def runGen(root, home, logFile, force):
    extraLogName = "d2p.log"
    cnfName  = home + "/" + root
    nnfName  = home + "/" + root
    cpogName = home + "/" + root
    if not certSSAT:    # model counting certification
        cnfName  = cnfName  + ".cnf"   
        nnfName  = nnfName  + ".nnf"
        cpogName = cpogName + ".cpog"
    elif not oneSided:  # verify SSAT upper trace
        cnfName  = cnfName  + ".sdimacs"   
        nnfName  = nnfName  + "_up.nnf"
        cpogName = cpogName + "_up.cpog"
    else:               # verify SSAT lower trace
        cnfName  = cnfName  + ".sdimacs"   
        nnfName  = nnfName  + "_low.nnf"
        cpogName = cpogName + "_low.cpog"
    if not force and os.path.exists(cpogName):
        return True
    progPrefix = ""
    if certSSAT:
        progPrefix = "../"
    cmd = [progPrefix + genProgram]
    if verbLevel != 1:
        cmd += ['-v', str(verbLevel)]
    if oneSided:
        cmd += ['-1']
    if monolithic:
        cmd += ['-m']
    if not useLemma:
        cmd += ['-e']
    if not group:
        cmd += ['-s']
    if certSSAT:
        cmd += ['-S']
    cmd += ["-C", str(clauseLimit), "-L", extraLogName, cnfName, nnfName, cpogName]
    ok = runProgram("GEN", root, cmd, logFile, extraLogName = extraLogName)
    checkFile("GEN", cpogName, logFile)
    if not ok and os.path.exists(cpogName):
        os.remove(cpogName)
    return ok

def runCheck(root, home, logFile):
    cnfName  = home + "/" + root 
    cpogName = home + "/" + root 
    if not certSSAT:    # model counting certification
        cnfName  = cnfName  + ".cnf"   
        cpogName = cpogName + ".cpog"
    elif not oneSided:  # verify SSAT upper trace
        cnfName  = cnfName  + ".sdimacs"   
        cpogName = cpogName + "_up.cpog"
    else:               # verify SSAT lower trace
        cnfName  = cnfName  + ".sdimacs"   
        cpogName = cpogName + "_low.cpog"
    progPrefix = ""
    if certSSAT:
        progPrefix = "../"
    cmd = [progPrefix + checkProgram]
    if verbLevel != 1:
        cmd += ['-v', str(verbLevel)]
    if oneSided:
        cmd += ['-1']
    if certSSAT:
        cmd += ['-S']
    cmd += [cnfName, cpogName]
    ok =  runProgram("FCHECK", root, cmd, logFile)
    return ok

def runLeanCheck(root, home, logFile):
    cnfName = home + "/" + root + ".cnf"
    cpogName = home + "/" + root + ".cpog"
    cmd = [leanCheckProgram]
    cmd += ["-c", cnfName, cpogName]
    ok =  runProgram("LCHECK", root, cmd, logFile)
    return ok


def runSequence(root, home, force):
    global oneSided
    result = ""
    prefix = "OVERALL"
    start = datetime.datetime.now()
    extension = "log"
    if oneSided:
        extension = "onesided_" + extension
    if monolithic:
        extension = "monolithic_" + extension
    if not useLemma:
        extension = "nolemma_" + extension
    if not group:
        extension = "split_" + extension
    if useLean:
        extension = "lean_" + extension
    if certSSAT:
        extension = "ssat_" + extension
    logName = root + "." + extension
    try:
        logFile = open(logName, 'w')
    except:
        print("%s. %s ERROR:Couldn't open file '%s'" % (root, prefix, logName))
        return
    ok = False
    done = False
    if certSSAT:
        ok = runSharpSSAT(root, home, logFile, force)
    else:
        ok = runD4(root, home, logFile, force)
    # SSAT
    if certSSAT:
        # Perform SSAT evaluation and levelized checking on upper and lower traces
        ok = ok and runEvalSSAT(root, home, logFile, force)
        #If ssat certification is enabled, start with proving lower trace first
        oneSided = True 
    ok = ok and runGen(root, home, logFile, force)
    if useLean and not certSSAT:
        ok = ok and runLeanCheck(root, home, logFile)
    else:
        ok = ok and runCheck(root, home, logFile)
    # Prove upper trace for ssat certification 
    if certSSAT and not lowBound_isOne(root, home, logFile):
        oneSided = False 
        ok = ok and runGen(root, home, logFile, force)
        ok = ok and runCheck(root, home, logFile)

    delta = datetime.datetime.now() - start
    seconds = delta.seconds + 1e-6 * delta.microseconds
    result += "%s LOG: Elapsed time = %.3f seconds\n" % (prefix, seconds)
    outcome = "normal" if ok else "failed"
    result += "%s OUTCOME: %s\n" % (prefix, outcome)
    print("%s. %s OUTCOME: %s" % (root, prefix, outcome))
    print("%s. %s Elapsed time: %.3f seconds" % (root, prefix, seconds))
    print("%s. %s. Results written to %s" % (root, prefix, logName))
    logFile.write(result)
    logFile.close()

def stripSuffix(fname):
    fields = fname.split(".")
    if len(fields) > 1:
        fields = fields[:-1]
    return ".".join(fields)


def runBatch(home, fileList, force):
    roots = [stripSuffix(f) for f in fileList]
    roots = [r for r in roots if r is not None]
    print("Running on roots %s" % roots)
    for r in roots:
        runSequence(r, home, force)

def run(name, args):
    global verbLevel, useLemma, group, oneSided, monolithic, useLean, certSSAT 
    home = "."
    force = True
    optList, args = getopt.getopt(args, "hv:1mLGFSs:")
    for (opt, val) in optList:
        if opt == '-h':
            usage(name)
            return
        elif opt == '-v':
            verbLevel = int(val)
        elif opt == '-1':
            oneSided = True
        elif opt == '-m':
            monolithic = True
        elif opt == '-L':
            useLemma = False
        elif opt == '-G':
            group = False
        elif opt == '-F':
            useLean = True
            force = False
        elif opt == '-S':
            certSSAT = True
        else:
            print("Unknown option '%s'" % opt)
            usage(name)
            return
    runBatch(home, args, force)

if __name__ == "__main__":
    run(sys.argv[0], sys.argv[1:])
    sys.exit(0)

