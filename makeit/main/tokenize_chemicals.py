from makeit.utils.parsing import SplitChemicalName 
from keras.preprocessing.text import Tokenizer # text pre-processing
import datetime
import cPickle
import json
import sys  # for commanad line
import os

def get_tokenizer_fpath():
	'''Returns file path where tokenizer is backed up'''
	fpath_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models')
	return os.path.join(fpath_root, 'tokenizer.cpickle')

def build_tokenizer(data_fname, N = 10000):
	'''This function trains a keras.preprocessing.text.Tokenizer on a set
	of data in .json form, where the .json file must be a list of chemical 
	names.'''

	# Initialize tokenizer
	tokenizer = Tokenizer(nb_words = None, filters = '', lower = True, 
		split = ' ')

	# Load data
	data_fid = open(data_fname, 'r')
	data = json.load(data_fid)
	print '...loaded data from {}'.format(data_fname)

	# Convert punctuation to spaces
	data = [' '.join(SplitChemicalName(name)) for name in data]

	# Iterate through now to build list
	tokenizer.fit_on_texts(data)
	print '...fit tokenizer on texts'

	# Print example
	name = data[0]
	print 'EXAMPLE:'
	print '    ' + name
	print '    ' + str(tokenizer.texts_to_sequences([name]))

	# Return trained tokenizer
	return tokenizer

def save_tokenizer(tokenizer, data_fname):
	'''Saves tokenizer object according to the filename defined
	in makeit.main.tokenize_chemicals.py'''
	# Dump data
	fpath = get_tokenizer_fpath()
	cPickle.dump(tokenizer, open(fpath, 'wb'))

	# Write to info file
	info_fid = open(fpath + '.info', 'w')
	time_now = datetime.datetime.utcnow()
	info_fid.write('{} generated at UTC {}\n\n'.format(fpath, time_now))
	info_fid.write('File details\n------------\n')
	info_fid.write('- data source: {}\n'.format(data_fname))
	info_fid.write('- document count: {}\n'.format(tokenizer.document_count))
	info_fid.write('- vocabulary size: {}\n'.format(len(tokenizer.word_counts)))
	info_fid.close()

	print '...saved tokenizer to {}'.format(get_tokenizer_fpath())
	return True

def load_tokenizer():
	'''Loads tokenizer object according to the filename defined
	in makeit.main.tokenize_chemicals.py'''
	return cPickle.load(open(get_tokenizer_fpath(), 'rb'))

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print('Usage: {} "data_file.json" [max # vocab]'.format(sys.argv[0]))
		print('    data_file.json must be a list of chemical names')
		quit(1)

	# Build
	if len(sys.argv) == 3:
		tokenizer = build_tokenizer(sys.argv[1], int(sys.argv[2]))
	else:
		tokenizer = build_tokenizer(sys.argv[1])

	# Save
	save_tokenizer(tokenizer, sys.argv[1])