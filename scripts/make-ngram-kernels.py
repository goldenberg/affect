#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-07-23.
Copyright (c) 2009. All rights reserved.
"""

import sys
import optparse
import logging
import subprocess
import os

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

logging.basicConfig()
log = logging.getLogger('make-kernels')

def main():
    usage = """%prog [options] DIRECTORY
            """
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    #opt_parser.add_option("-l", "--log_level", action="store_true", 
    #                   default='warning', dest="log_level")
    
    options, arguments = opt_parser.parse_args()
    #log.setLevel(LOG_LEVELS[opt_parser.log_level])
    log.setLevel(logging.DEBUG)
    
    walk_directory(arguments[0])

def walk_directory(top_directory):
    '''
    Walk through the directories, looking for *.fstlist files. If one is
    found, creates a 1 and 2-gram kernel and assumes there is a symbol file
    at *.fstlist/../fsts/symbol_table.tsv
    '''
    for (dirpath, dirnames, filenames) in os.walk(top_directory):
        for filename in filenames:
            if filename.endswith('.fstlist'):
                symbol_path = os.path.join(dirpath , 'fsts', 'symbol_table.tsv')
                
                if not os.path.exists(symbol_path):
                    log.error('There is not a symbol file at %s' % symbol_path)
                else:
                    sigma = determine_alphabet_size(symbol_path)
                    fstlist = os.path.join(dirpath, filename)
                    create_kernel(sigma, 1, fstlist)
                    create_kernel(sigma, 2, fstlist)
    
def create_kernel(alphabet_size, order, fstlist):
    '''
    Creates an n-gram using klngram with specified alphabet size and order.
    '''
    kernel_path = os.path.join( os.path.dirname(fstlist), '%i-gram.kar' % order)
    kernel_file = open(kernel_path, 'wb')
    
    arguments = ['klngram', 
                 '--sigma=%i' % alphabet_size,
                 '--order=%i' % order,
                 fstlist]
    
    log.info(' '.join(arguments))
    subprocess.call(arguments, stdout=kernel_file, stderr=open('/dev/null', 'w'))
    
    kernel_file.close()

def compile_kernel(kernel_filename):
    '''
    Compiles a kernel into a libsvm compatible matrix .kar file using kleval.
    '''
    matrix_filename = os.path.splitext(kernel_filename)[0] + '.matrix.kar'
    matrix_file = open(matrix_filename, 'wb')
    
    arguments = ['kleval',
                 '--libsvm',
                 '--kar',
                 kernel_filename]
    
    log.info(' '.join(arguments))
    
    subprocess.call(arguments, stdout=matrix_file, stderr=open('/dev/null', 'w'))
    
    matrix_file.close()

def determine_alphabet_size(symbol_filename):
    '''
    Determines the number of symbols. i.e. counts the number of lines in a
    symbol_table file.
    '''
    
    sigma = 0
    
    for line in open(symbol_filename):
        if line.strip() != '':
            sigma += 1
    
    return sigma

if __name__ == "__main__":
    main()
