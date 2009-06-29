#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-06-11.
Copyright (c) 2009 __MyCompanyName__. All rights reserved.
"""

import sys
import optparse
import logging

logging.basicConfig(level=logging.DEBUG)

help_message = """%prog SVM_FILE NEW_SVM_FILE INDICES [options]
Creates a new SVM input file with only the specified vector indices. 
Fields can be specified as ranges.  For example, valid input is:

./filter_svmin.py input.svm output.svm 1-4 8 10-12

This would create a new output.svm file with vectors of length 8. Indices
will be renumbered starting from 1.
"""

def main():
    opt_parser = optparse.OptionParser(usage=help_message)
       
    options, arguments = opt_parser.parse_args()
    
    logging.debug("Options: %s Arguments: %s" % (options, arguments))
    
    input_filename  = arguments[0]
    output_filename = arguments[1]
    range_strings   = arguments[2:]
    
    indices = parse_ranges(range_strings)
    filter_file(input_filename, output_filename, indices)
    
def filter_file(input_filename, output_filename, indices):
    output_file = open(output_filename, 'w')
    
    logging.debug('Filtering for indices: %s' % indices)
    
    for line in open(input_filename):
        if line.strip() != '':
            the_class, original_vector = parse_line(line)
            new_vector = [original_vector[index-1] for index in indices]
            output_file.write(format_line(the_class, new_vector) + '\n')
    
    output_file.close()

def parse_ranges(ranges):
    '''
    Parses the range arguments into a list of 1-indexed list indices.
    
    >>> parse_ranges(['1-4', '8', '10-12'])
    [1, 2, 3, 4, 8, 10, 11, 12]
    '''
    indices = []
    
    for the_range in ranges:
        if '-' in the_range:
            start, begin = [int(x) for x in the_range.split('-')]
            indices.extend(range(start, begin+1))
        else:
            indices.append(int(the_range))
    
    return indices

def parse_line(line):
    '''
    Parses a libsvm formatted line. Returns a pair: the class and the vector
    as a list. All values are maintained as strings.
    
    >>> filter_svmin.parse_line("-1 1:165.051815792 2:61.948223114 3:468.129852295 4:32.1355681832 5:514.83689270")
    ('-1', ['165.051815792', '61.948223114', '468.129852295', '32.1355681832', '514.83689270'])
    '''
    fields = line.split(' ')
    the_class = fields[0]
    vector = [x.split(':')[1] for x in fields[1:]]
    
    return the_class, vector

def format_line(the_class, vector):
    '''
    Formats a line suitable for writing to an svm input file.
    '''
    line = '%s' % the_class
    
    for index, value in enumerate(vector):
        line += " %i:%s" % (index+1, value)
    
    return line

if __name__ == "__main__":
    main()
