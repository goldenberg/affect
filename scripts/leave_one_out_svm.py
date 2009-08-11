#!/usr/bin/env python
# encoding: utf-8
"""
leave_one_out_svm.py

Created by Benjamin Goldenberg on 2009-08-07.
Copyright (c) 2009. All rights reserved.
"""

import os
import sys
import optparse
import logging
import linecache
import subprocess
import re

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

SVM_TRAIN_PATH = '/g/reu09/goldenbe/OpenKernel/libsvm-2.82/svm-train'
SVM_PREDICT_PATH = '/g/reu09/goldenbe/OpenKernel/libsvm-2.82/svm-predict'

logging.basicConfig()
log = logging.getLogger('leave_one_out_svm')

def main():
    usage = """%prog INPUT_FILE TEMP_DIR SVM_ARGS
            """
    
    
    dataset_file = sys.argv[1]
    temp_dir = sys.argv[2]
    svm_args = sys.argv[3:]
    
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    output_basename = os.path.join(temp_dir, os.path.split(dataset_file)[1])
    # read lines and filter out any whitespace lines
    lines = open(dataset_file).readlines()    
    lines = filter(lambda line: line.strip() != '', lines)
    
    # write out all the split files
    [split_data(lines, i, output_basename) for i in range(1, len(lines)+1)]
    
    # run all svms
    successes = sum([run_svm(output_basename, i, svm_args) for i in range(1, len(lines)+1)])
    
    print '%i/%i successes (%.2f%% accuracy)' % (successes, len(lines), successes * 100.0 / len(lines))

def run_svm(output_basename, index, svm_args):
    """
    Runs svm-train and svm-predict on basename.index.{train, test}. Returns
    the percentage accuracy as a float [0,1] (should be 0 or 1 for leave one out)
    """
    train_file = '%s.%i.train' % (output_basename, index)
    test_file  = '%s.%i.test'  % (output_basename, index)
    model_file = '%s.%i.model' % (output_basename, index)
    output_file= '%s.%i.output'% (output_basename, index)
    
    train_args = [SVM_TRAIN_PATH] + svm_args + [train_file, model_file]
    train_proc = subprocess.Popen(train_args, stderr=subprocess.PIPE, 
                                    stdout=subprocess.PIPE)
    train_proc.communicate()
    
    test_args = [SVM_PREDICT_PATH, test_file, model_file, output_file]
    test_proc = subprocess.Popen(test_args, stderr=subprocess.PIPE, 
                                    stdout=subprocess.PIPE)
    
    stdout, stderr = test_proc.communicate()
    
    return parse_accuracy(stdout)

def parse_accuracy(stdout):
    """
    Looks for the string a back slash, which should be found as in (0/1) 
    and returns the percentage accuracy as a float.
    """
    
    # match numerator and denominator
    regex = re.compile('Accuracy = \d*.*\d*% \((\d*)/(\d*)\)')
    
    all_matches = regex.findall(stdout)
    
    if len(all_matches) >= 1 and len(all_matches[0]) != 2:
        log.error("Couldn't parse the accuracy for output: %s" % stdout)
    else:
        correct, possible = all_matches[0]
        return float(correct) / float(possible)

def split_data(lines, index, output_basename):
    """
    Splits an SVM input file into two files, one training file with n-1
    vectors and one test file with 1 vector. The files will be named
    output_basename.index.{train, test}
    """
    
    train = open('%s.%i.train' % (output_basename, index), 'w')
    test = open('%s.%i.test' % (output_basename, index), 'w')
    
    train.writelines(lines[:index-1] + lines[index:])
    test.write(lines[index-1])
    
    train.close()
    test.close()


if __name__ == "__main__":
    main()

