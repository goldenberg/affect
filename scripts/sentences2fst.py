#!/usr/bin/env python
# encoding: utf-8
"""
sentences2fst.py

Created by Benjamin Goldenberg on 2009-06-17.
Copyright (c) 2009 __MyCompanyName__. All rights reserved.
"""

import sys
import optparse
import logging
import subprocess
import random
import os
import re
import nltk
from nltk.corpus import wordnet
import linecache
from decimal import Decimal
import shutil

import pdb


LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

FST_TYPES = ('pos', 'words', 'lemmas', 'senti', 'anew')

# punctuation that is worth parsing as a separate token. all other punctuation
# is ignored. ellipses would be nice to parse as a token, but I couldn't figure
# out how to escape them.

SPECIAL_PUNCTUATION = ['?', '!', '&']

WORDNET_POS = { 'a' : ['JJ', 'JJR', 'JJS'], #adjectives
                'r' : ['RB', 'RBR', 'RBS'],
                'n' : ['NN', 'NNS', 'NNP', 'NNPS'],
                'v' : ['VB', 'VBD', 'VBG', 'VBN', 'VBZ']
}

logging.basicConfig()
log = logging.getLogger("sentences2fst")


def main():
    usage = """%prog [options] SENTENCE_DIRECTORY 
            """
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-l", "--log_level", action="store", 
                       default='debug', dest="log_level", 
                       help="Logging level. One of {'debug', 'info', 'warning', 'error', 'critical'}")
    
    opt_parser.add_option("-s", "--symbol_table", action='store', 
                       default='symbol_table.tsv', dest='symbol_table',
                       help='Filename to store the word symbol table.')
    
    opt_parser.add_option("-p", "--pos_directory", action='store', 
                        help="A directory of POS files to be read. Creates"
                        "a parallel path in the FST")
    
    options, arguments = opt_parser.parse_args()
    
    log.setLevel(LOG_LEVELS[options.log_level])
    
    fst_types, other_args = parse_args(arguments)
    
    sentence_directory = other_args[0]
    symbol_filename = options.symbol_table
    
    sentence_dicts = read_agree_sentence_directory(sentence_directory)
    
    for fst_type in fst_types:
        if fst_type in ('words', 'lemmas', 'pos'):
            tag_sentences(sentence_dicts, fst_type)
            write_many_simple_fsts(sentence_dicts, fst_type)

def parse_args(arguments):
    '''
    Returns a pair: a list of the fst output types and a list of any other args.
    
    >>> parse_args(['words', 'anew', './foo', './bar'])
    (['words', 'anew'], ['./foo', './bar'])
    '''
    fst_types = []
    other_args = []
    
    for arg in arguments:
        if arg in FST_TYPES:
            fst_types.append(arg)
        else:
            other_args.append(arg)
    
    return fst_types, other_args

def read_agree_sentence_directory(sentence_directory):
    '''
    Reads a directory of high agree sentences into sentence dicts.
    '''
    sentence_dicts = []
    
    for sent_filename in os.listdir(sentence_directory):
        full_path = os.path.join(sentence_directory, sent_filename)
        sentence_dicts.extend(read_agree_sents(full_path))
    
    return sentence_dicts

def read_agree_sents(filename):
    '''
    Returns a list of dictionaries with 4 keys:
    
    1) 'id' : sentence id (int)
    2) 'emotion' : emotion id (int)
    3) 'words' : the parsed words and interesting punctuation (list of strings)
    4) 'pos'
    '''
    
    result = []
    story_name = os.path.splitext(os.path.basename(filename))[0]
    
    for line in open(filename):
        if line.strip() != '':
            fields = line.split('@')
            if len(fields) == 3:
                sentence_id = int(fields[0])
                emotion = int(fields[1])
                words = nltk.word_tokenize(fields[2])
                
                sent_dict = {      'id' : sentence_id,
                              'emotion' : emotion,
                                'words' : words
                            }
                
                result.append(sent_dict)
            else:
                log.error('This line did not have 3 fields as expected: %s' % line)
                
                
    return result

def tag_sentences(sentence_dicts, tag_type):
    # check if it's already been tagged
    if tag_type in sentence_dicts[0]:
        return
    
    if tag_type == 'pos':
        [pos_tag_sentence(sent) for sent in sentence_dicts]
    elif tag_type == 'lemmas':
        tag_sentences(sentence_dicts, 'pos')
        [lemmatize_sentence(sent) for sent in sentence_dicts]
    elif tag_type == 'words':
        # do nothing for words
        pass


def pos_tag_sentence(sent_dict):
    '''
    Creates part of speech tags for each word in the sentence.
    
    >>> sent = {'words' : ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
    >>> pos_tag_sentence(sent)
    >>> sent['pos']
    ('IN', 'DT', 'NN', 'VBD', 'PRP', 'PRP$', 'NN', ',', 'CC', 'IN', 'JJ', 'NN', 'VBD', 'NN', 'IN', 'PRP', '.')
    '''
    
    word_tag_pairs = nltk.pos_tag(sent_dict['words'])
    
    # unzip the pairs using zip(*)
    sent_dict['pos'] = zip(*word_tag_pairs)[1]

def lemmatize_sentence(sent_dict):
    '''
    Adds lemmas to the sent_dict using the WordNet lemmatizer. It will be
    more accurate if pos tags also exist. If they don't, it will try them all
    until it finds one that creates a new lemma.
    
    >>> sent = {'words': ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
    >>> lemmatize_sentence(sent)
    >>> sent['lemmas']
    ['So', 'the', 'father', 'give', 'him', 'his', 'bless', ',', 'and', 'with', 'great', 'sorrow', 'take', 'leave', 'of', 'him', '.']
    
    >>> sent = {'pos': ('IN', 'DT', 'NN', 'VBD', 'PRP', 'PRP$', 'NN', ',', 'CC', 'IN', 'JJ', 'NN', 'VBD', 'NN', 'IN', 'PRP', '.'), 'words': ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
    >>> lemmatize_sentence(sent)
    >>> sent['lemmas']
    ['So', 'the', 'father', 'give', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'take', 'leave', 'of', 'him', '.']
    '''
    if 'pos' in sent_dict:
        # use the POS tags
        lemmas = []
        for word, pos in zip(sent_dict['words'], sent_dict['pos']):
            lemmas.append(lemmatize_word(word, pos))
            
        sent_dict['lemmas'] = lemmas
    else:
        sent_dict['lemmas'] = [lemmatize_word(word) for word in sent_dict['words']]

def tag_swn_sentence(sent_dict, sentiwordnet):
    '''
    Looks up each lemma in SentiWordNet, by using the first synset for each
    lemma. If the word cannot be found, scores of 0 will be assigned. In order
    to look up each word in SentiWordnet, the words will be lemmatized and
    POS-tagged if they haven't been yet.
    '''
    
    if 'pos' not in sent_dict:
        pos_tag_sentence(sent_dict)
    
    if 'lemmas' not in sent_dict:
        lemmatize_sentence(sent_dict)
    
    pos_swn = []
    neg_swn = []
    
    for lemma, pos in zip(sent_dict['lemmas'], sent_dict['pos']):
        synsets = wordnet.synsets(lemma, wordnet_pos(pos))
        print synsets
        if synsets != []:
            first_synset_pair = (synsets[0].pos, synsets[0].offset)
            
            if first_synset_pair in sentiwordnet:
                swn_values = sentiwordnet[first_synset_pair]
                
                pos_value = swn_values['pos']
                neg_value = swn_values['neg']
            else:
                pos_value = neg_value = 0.0
        else:
            pos_value = neg_value = 0.0
        
        pos_swn.append(pos_value)
        neg_swn.append(neg_value)
    
    sent_dict['senti'] = {'pos' : pos_swn, 'neg' : neg_swn}

def read_sentiwordnet(path):
    '''
    Returns a dictionary keyed by the pair (POS, offset). Each value is also
    a dictionary with three keys: 'pos', 'neg', 'terms'.
    
    >>> swn = read_sentiwordnet('/Users/bpg/cslu/affect/word_data/SentiWordNet_1.0.1.txt')
    >>> swn[('a', 1005286)] == {'neg': 0.125, 'terms': ['forlorn#a#1', 'godforsaken#a#2', 'lorn#a#1', 'desolate#a#2'], 'pos': 0.25}
    True
    '''
    sentiwordnet = {}
    
    for line in open(path):
        if not line.startswith('#') and line.strip() != '':
            fields = line.split()
            
            key = (fields[0], int(fields[1]))
            
            sentiwordnet[key] = { 'pos' : float(fields[2]),
                                  'neg' : float(fields[3]),
                                  'terms' : fields[4:]
                                }
    
    return sentiwordnet

def read_anew_db(path):
    '''
    Reads the ANEW.txt file into a dictionary keyed by word. Each value is
    also a dictionary with the following structure:
    
    {'abduction' : { 'word_num' : 621,
                    'frequency' : 1,
                      'valence' : { 'mean' : 2.76,
                                   'stdev' : 2.06},
                      'arousal' : { 'mean' : 5.53,
                                   'stdev' : 2.43},
                    'dominance' : { 'mean' : 3.49,
                                   'stdev' : 2.38}
                   }
    }
    
    >>> anew = read_anew_db('/Users/bpg/cslu/affect/word_data/anew_all.txt')
    >>> anew['village'] == {'arousal': {'stdev': Decimal('1.87'), 'mean': Decimal('4.08')}, 'word_num': 477, 'valence': {'stdev': Decimal('1.34'), 'mean': Decimal('5.92')}, 'frequency': 72, 'dominance': {'stdev': Decimal('1.74'), 'mean': Decimal('4.94')}}
    True
    '''
    anew_dict = {}
    for line in open(path):
        fields = line.split('\t')
        
        if len(fields) == 9 and fields[1] != 'WdNum':
            if fields[8].startswith('.'):
                frequency = 0
            else:
                frequency = int(fields[8])
            
            word_dict = {  'word_num' : int(fields[1]),
                            'valence' : { 'mean' : Decimal(fields[2]),
                                         'stdev' : Decimal(fields[3])},
                            'arousal' : { 'mean' : Decimal(fields[4]),
                                         'stdev' : Decimal(fields[5])},
                          'dominance' : { 'mean' : Decimal(fields[6]),
                                         'stdev' : Decimal(fields[7])},
                          'frequency' : frequency         
            }
            
            anew_dict[fields[0]] = word_dict
    
    return anew_dict

def read_pos_sentence(sentence_id, story, pos_directory):
    '''
    Reads the parts of speech and the words for a specified sentence in a
    given story. The sentence_id is a 0-indexed int from the *.agree files.
    Returns a dictionary with two keys:
    
    words: a list of stemmed words
    pos: a list of parts of speech (as defined in the original corpus)
    
    words and pos should be the same length (so, they can easily be zipped together)
    '''
    word_list = []
    pos_list  = []
    
    filename = os.path.join(pos_directory, '%s.sent.okpuncs.props.pos' % story)
    
    line = linecache.getline(filename, sentence_id+1)
    
    for token in re.findall('\(.*?\)', line):
        # each token will be of the form (POS Word) (e.g. (RB Long))
        fields = token.split()
        pos = fields[0][1:]
        word = fields[1][:-1]
        
        if word.isalpha():
            word = lemmatize_word(word, pos)
            word_list.append(word.upper())
            pos_list.append(pos)
        else:
            if word in SPECIAL_PUNCTUATION:
                word_list.append(word)
                pos_list.append('.')
                
    assert len(word_list) == len(pos_list)
    
    return {'words' : word_list, 'pos' : pos_list}

def create_symbol_table(sentence_dicts, key, filename):
    '''
    Writes a symbol table in the AT&T format to the specified filename.
    '''
    symbols = set()
    
    counter = 1
        
    f = open(filename, 'w')
    
    # write words
    for sent_dict in sentence_dicts:
        for word in sent_dict[key]:
            if word not in symbols:
                f.write('%s\t%i\n' % (word, counter))
                
                symbols.add(word)
                counter += 1
    
    f.close()

def write_many_simple_fsts(sent_dicts, key, basepath='./fsts_'):
    '''
    Writes a list of fsts to a directory. First creates a directory by
    appending key to basepath and writes over any existing directory.
    Then, writes a symbol file. Then, calls write_simple_fst for each 
    sentence. Finally creates an FST list file.
    '''
    fst_directory = basepath + key
    symbol_path = os.path.join(fst_directory, "symbol_table.tsv")
    
    if os.path.exists(fst_directory):
        shutil.rmtree(fst_directory)
        
    os.mkdir(fst_directory)
    
    create_symbol_table(sent_dicts, key, symbol_path)
    
    for sent_no, sent_dict in enumerate(sent_dicts):
        fst_basepath = os.path.join(fst_directory, str(sent_no))
        
        write_simple_fst(sent_dict[key], symbol_path, fst_basepath)
        
    write_fst_list(sent_dicts, fst_directory)
    write_svm_input(sent_dicts, fst_directory)

def write_simple_fst(symbols, symbol_path, fst_basepath):
    '''
    Writes a simple fst containing a single path of symbols with no weights.
    A text representation of the FST is written to fst_path + ".txt" and then
    it is compile into a binary using fstcompile.
    '''
    fst = open(fst_basepath + ".txt", "w")
    
    # write arcs with each word
    state = 1
    for symbol in symbols:
        write_arc(fst, state, state+1, symbol, symbol)
        state += 1
    
    # write final state
    fst.write(str(state))
    fst.close()
    
    parameters = [ "fstcompile", 
                   "--arc_type=log",
                   "--isymbols=%s" % symbol_path, 
                   "--osymbols=%s" % symbol_path, 
                   fst_basepath + ".txt", 
                   fst_basepath + ".fst"]
    
    subprocess.call(parameters)

def write_arc(f, start_state, end_state, input_label, output_label):
    arc_fields = [str(start_state), str(end_state), input_label, output_label]
    f.write('\t'.join(arc_fields) + '\n')

def lemmatize_word(word, pos=None):
    '''
    Tries to lemmatize a word. If a POS is specified, it uses the corresponding 
    Wordnet tag, if possible. If a POS is not specified, all the tags are tried
    until a different word is returned. If nothing is found, return the original
    word.
    
    >>> lemmatize_word('youngest', 'JJS')
    'young'
    >>> lemmatize_word('brought', 'VBD')
    'bring'
    
    '''
    lemmatizer = nltk.stem.WordNetLemmatizer()
    
    
    if pos:
        wordnet_pos_tag = wordnet_pos(pos)
    else:
        wordnet_pos_tag = None
    
    if wordnet_pos_tag:
        return lemmatizer.lemmatize(word, wordnet_pos_tag)
    else:
        for tag in ['a', 'r', 'n', 'v']:
            root = lemmatizer.lemmatize(word, tag)
            if root != word:
                return root
    
    # if we haven't found anything by here, just return the word.
    return word

def wordnet_pos(pos_tag):
    '''
    Returns 'a', 'r', 'n', or 'v' corresponding to adjective, adverb, noun
    and verb, respectively. Return None if there's no match
    '''
    
    prefixes = { 'JJ' : 'a',
                 'NN' : 'n',
                 'RB' : 'r',
                 'VB' : 'v'
    }
    
    return prefixes.get(pos_tag[:2])

def write_fst_list(sentence_dicts, fst_directory):
    """
    Writes an fst list file inside fst_directory for all of the sentences. 
    Line numbers should correspond to sentence indices in list of dicts. 
    """
    list_file_path = os.path.join(fst_directory, 'fst.list')
    
    f = open(list_file_path, 'w')
    
    for index in range(1, len(sentence_dicts)+1):
        f.write('%i.fst\n' % index)
    
    f.close()

def write_svm_input(sentence_dicts, fst_directory, train_percentage=0.8):
    '''
    Writes test and train files for input to LIBSVM. Also writes a file 
    containing all of the sentences
    '''
    train_path = os.path.join(fst_directory, 'sentences.train')
    test_path = os.path.join(fst_directory, 'sentences.test')
    all_path = os.path.join(fst_directory, 'sentences.all')
    
    
    training_size = int(round(train_percentage*len(sentence_dicts)))
    train_list = random.sample(sentence_dicts, training_size)
    
    
    train_file = open(train_path, 'w')
    test_file  = open(test_path, 'w')
    all_file = open(all_path, 'w')
    
    for index, sent_dict in enumerate(sentence_dicts):
        line = '%s %i:1.0\n' % (sent_dict['emotion'], index+1)
        if sent_dict in train_list:
            train_file.write(line)
        else:
            test_file.write(line)
        
        all_file.write(line)
    
    train_file.close()
    test_file.close()
    all_file.close()


if __name__ == "__main__":
    if sys.argv[1] == 'test':
        import doctest
        doctest.testmod(verbose=False)
    else:
        main()
