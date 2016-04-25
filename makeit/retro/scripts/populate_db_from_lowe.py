## Meant to use with Daniel Lowe's patent database
# reaction SMILES strings only (for now)

from __future__ import print_function
import argparse
from numpy.random import shuffle # for random selection
import rdkit.Chem as Chem          # molecule building
from rdkit.Chem import AllChem
from collections import defaultdict
import rdkit.Chem.Draw as Draw
from rdkit import RDLogger
import datetime # for info files
import json # for dumping
import sys  # for commanad line
import os   # for file paths
import re 
import itertools

# DATABASE
from pymongo import MongoClient    # mongodb plugin
client = MongoClient('mongodb://guest:guest@rmg.mit.edu/admin', 27017)
db = client['askcos_transforms']
collection = db['lowe']

def mols_from_smiles_list(all_smiles):
	'''Given a list of smiles strings, this function creates rdkit
	molecules'''
	mols = []
	for smiles in all_smiles:
		if not smiles: continue
		mols.append(Chem.MolFromSmiles(smiles))
	return mols

def bond_to_label(bond):
	'''This function takes an RDKit bond and creates a label describing
	the most important attributes'''
	# atoms = sorted([atom_to_label(bond.GetBeginAtom().GetIdx()), \
	# 			    atom_to_label(bond.GetEndAtom().GetIdx())])
	atoms = sorted([bond.GetBeginAtom().GetAtomicNum(), \
					bond.GetEndAtom().GetAtomicNum()])

	return '{}{}{}'.format(atoms[0], bond.GetSmarts(), atoms[1])

def get_tagged_atoms_from_mols(mols):
	'''Takes a list of RDKit molecules and returns total list of
	atoms and their tags'''
	atoms = []
	atom_tags = []
	for mol in mols:
		new_atoms, new_atom_tags = get_tagged_atoms_from_mol(mol)
		atoms += new_atoms 
		atom_tags += new_atom_tags
	return atoms, atom_tags

def get_tagged_atoms_from_mol(mol):
	'''Takes an RDKit molecule and returns list of tagged atoms and their
	corresponding numbers'''
	atoms = []
	atom_tags = []
	for atom in mol.GetAtoms():
		if ':' in atom.GetSmarts():
			atoms.append(atom)
			atom_tags.append(atom.GetSmarts().split(':')[1][:-1])
	return atoms, atom_tags

def atoms_are_different(atom1, atom2, level = 1):
	'''Compares two RDKit atoms based on basic properties'''

	if atom1.GetSmarts() != atom2.GetSmarts(): return True # should be very general
	if atom1.GetAtomicNum() != atom2.GetAtomicNum(): return True # must be true for atom mapping
	if atom1.GetTotalNumHs() != atom2.GetTotalNumHs(): return True
	if atom1.GetFormalCharge() != atom2.GetFormalCharge(): return True
	if atom1.GetDegree() != atom2.GetDegree(): return True
	if atom1.IsInRing() != atom2.IsInRing(): return True
	if atom1.GetNumRadicalElectrons() != atom2.GetNumRadicalElectrons(): return True
	# TODO: add # pi electrons like ICSynth?

	# Check bonds and nearest neighbor identity
	if level >= 1:
		bonds1 = sorted([bond_to_label(bond) for bond in atom1.GetBonds()]) 
		bonds2 = sorted([bond_to_label(bond) for bond in atom2.GetBonds()]) 
		if bonds1 != bonds2: return True

		# # Check neighbors too (already taken care of with previous lines)
		# neighbors1 = sorted([atom.GetAtomicNum() for atom in atom1.GetNeighbors()])
		# neighbors2 = sorted([atom.GetAtomicNum() for atom in atom2.GetNeighbors()])
		# if neighbors1 != neighbors2: return True

	return False

def get_changed_atoms(reactants, products):
	'''Looks at mapped atoms in a reaction and determines which ones changed'''

	err = 0
	prod_atoms, prod_atom_tags = get_tagged_atoms_from_mols(products)

	if v: print('Products contain {} tagged atoms'.format(len(prod_atoms)))
	if v: print('Products contain {} unique atom numbers'.format(len(set(prod_atom_tags))))

	reac_atoms, reac_atom_tags = get_tagged_atoms_from_mols(reactants)
	if len(set(prod_atom_tags)) != len(set(reac_atom_tags)):
		if v: print('warning: different atom tags appear in reactants and products')
		err = 1
	if len(prod_atoms) != len(reac_atoms):
		if v: print('warning: total number of tagged atoms differ, stoichometry != 1?')
		#err = 1

	# Find differences 
	changed_atoms = []
	changed_atom_tags = []
	#print(reac_atom_tags)
	#print(prod_atom_tags)

	# Product atoms that are different from reactant atom equivalent
	for i, prod_tag in enumerate(prod_atom_tags):

		for j, reac_tag in enumerate(reac_atom_tags):
			if reac_tag != prod_tag: continue
			if reac_tag not in changed_atom_tags: # don't bother comparing if we know this atom changes
				# If atom changed, add
				if atoms_are_different(prod_atoms[i], reac_atoms[j]):
					changed_atoms.append(reac_atoms[j])
					changed_atom_tags.append(reac_tag)
					break
				# If reac_tag appears multiple times, add (need for stoichometry > 1)
				if prod_atom_tags.count(reac_tag) > 1:
					changed_atoms.append(reac_atoms[j])
					changed_atom_tags.append(reac_tag)
					break

	# Reactant atoms that do not appear in product (tagged leaving groups)
	for j, reac_tag in enumerate(reac_atom_tags):
		if reac_tag not in changed_atom_tags:
			if reac_tag not in prod_atom_tags:
				changed_atoms.append(reac_atoms[j])
				changed_atom_tags.append(reac_tag)

	if v: 
		print('{} tagged atoms in reactants change 1-atom properties'.format(len(changed_atom_tags)))
		for smarts in [atom.GetSmarts() for atom in changed_atoms]:
			print('  {}'.format(smarts))

	return changed_atoms, changed_atom_tags, err

def draw_reaction_smiles(rxn_smiles, fpath = 'test.png'):

	opts = Draw.DrawingOptions()
	opts.elemDict = defaultdict(lambda: (0,0,0))
	opts.noCarbonSymbols = False
	opts.selectColor = (1, 0, 0)

	rxn = AllChem.ReactionFromSmarts(rxn_smiles)
	img = Draw.ReactionToImage(rxn, subImgSize = (300, 300), highlightAtoms = [], options = opts)
	img.save(fpath)

	try:
		fpath2 = fpath.replace('.', '_clean.')
		new_rxn_string = ''
		for i in range(rxn.GetNumReactantTemplates()):
			mol = rxn.GetReactantTemplate(i); mol.SetProp('_Name', 'temp')
			new_rxn_string += Chem.MolToSmiles(Chem.MolFromTPLBlock(Chem.MolToTPLBlock(mol)), isomericSmiles = True) + '.'
		new_rxn_string = new_rxn_string[:-1] + '>>'
		for j in range(rxn.GetNumProductTemplates()):
			mol = rxn.GetReactantTemplate(j); mol.SetProp('_Name', 'temp')
			new_rxn_string += Chem.MolToSmiles(Chem.MolFromTPLBlock(Chem.MolToTPLBlock(mol)), isomericSmiles = True) + '.'
		rxn2 = AllChem.ReactionFromSmarts(new_rxn_string[:-1])
		opts.noCarbonSymbols = True
		img = Draw.ReactionToImage(rxn2, subImgSize = (300, 300), highlightAtoms = [], options = opts)
		img.save(fpath2)
	except Exception as e:
		if v: print('warning: failed to draw clean transform')

	return

def expand_atoms_to_use(mol, atoms_to_use, groups = [], symbol_replacements = []):
	'''Given an RDKit molecule and a list of AtomIdX which should be included
	in the reaction, this function expands the list of AtomIdXs to include one 
	nearest neighbor with special consideration of (a) unimportant neighbors and
	(b) important functional groupings'''

	# Copy
	new_atoms_to_use = atoms_to_use[:]

	# Look for all atoms in the current list of atoms to use
	for atom in mol.GetAtoms():
		if atom.GetIdx() not in atoms_to_use: continue
		# Look for all nearest neighbors of the currently-included atoms
		for neighbor in atom.GetNeighbors():
			# Evaluate nearest neighbor atom to determine what should be included
			new_atoms_to_use, symbol_replacements = \
					expand_atoms_to_use_atom(mol, new_atoms_to_use, neighbor.GetIdx(), 
						groups = groups, symbol_replacements = symbol_replacements)
			
	return new_atoms_to_use, symbol_replacements

def expand_atoms_to_use_atom(mol, atoms_to_use, atom_idx, groups = [], symbol_replacements = []):
	'''Given an RDKit molecule and a list of AtomIdx which should be included
	in the reaction, this function extends the list of atoms_to_use by considering 
	a candidate atom extension, atom_idx'''

	# Skip current candidate atom if it is already included
	if atom_idx in atoms_to_use:
		return atoms_to_use, symbol_replacements
	
	# Include this atom no matter what
	atoms_to_use.append(atom_idx)

	# See if this atom belongs to any groups
	found_in_group = False
	for group in groups:
		if int(atom_idx) in group: # int correction
			if v: print('added group centered at {}'.format(atom_idx))
			# Add the whole list, redundancies don't matter
			atoms_to_use.extend(list(group)) 
			found_in_group = True

	# How do we add an atom that wasn't in an identified important functional group?
	# Develop special SMARTS symbol
	if not found_in_group:		
		symbol_replacements.append((atom_idx, convert_atom_to_wildcard(mol.GetAtomWithIdx(atom_idx))))

	return atoms_to_use, symbol_replacements

def convert_atom_to_wildcard(atom):
	'''This function takes an RDKit atom and turns it into a wildcard 
	using hard-coded generalization rules. This function should be used
	when candidate atoms are used to extend the reaction core for higher
	generalizability'''

	# Is this a terminal atom? We can tell if the degree is one
	if atom.GetDegree() == 1:
		return atom.GetSmarts()
		# # Be explicit about number of hydrogens (since it's terminal!)
		# smarts = atom.GetSmarts()
		# if ':' in atom.GetSmarts():
		# 	return smarts.replace(':', ';H{}:'.format(atom.GetTotalNumHs()))
		# elif ']' in atom.GetSmarts():
		# 	return smarts.replace(']', ';H{}]'.format(atom.GetTotalNumHs()))
		# else:
		# 	return '[' + smarts + ';H{}]'.format(atom.GetTotalNumHs())

	# Initialize
	symbol = '['

	# Add atom primitive (don't use COMPLETE wildcards)
	if atom.GetAtomicNum() != 6:
		symbol += '#{};'.format(atom.GetAtomicNum())
	elif atom.GetIsAromatic():
		symbol += 'c;'
	else:
		symbol += 'C;'

	# Charge is important
	if atom.GetFormalCharge() != 0:
		charges = re.search('([-+]+[1-9]?)', atom.GetSmarts())
		if charges: symbol += charges.group() + ';'

	# Strip extra semicolon
	if symbol[-1] == ';': symbol = symbol[:-1]

	# Close with label or with bracket
	label = re.search('\:[0-9]+\]', atom.GetSmarts())
	if label: 
		symbol += label.group()
	else:
		symbol += ']'

	if v: 
		if symbol != atom.GetSmarts():
			print('Improved generality of atom SMARTS {} -> {}'.format(atom.GetSmarts(), symbol))

	return symbol

def get_fragments_for_changed_atoms(mols, changed_atom_tags, radius = 0, 
	category = 'reactants', expansion = []):
	'''Given a list of RDKit mols and a list of changed atom tags, this function
	computes the SMILES string of molecular fragments using MolFragmentToSmiles 
	for all changed fragments'''

	fragments = ''
	for mol in mols:
		# Initialize list of replacement symbols (updated during expansion)
		symbol_replacements = []

		# Are we looking for groups? (reactants only)
		if category == 'reactants':
			groups = get_special_groups(mol)
		else:
			groups = []

		# Build list of atoms to use
		atoms_to_use = []
		for atom in mol.GetAtoms():
			# Check self (only tagged atoms)
			if ':' in atom.GetSmarts():
				if atom.GetSmarts().split(':')[1][:-1] in changed_atom_tags:
					atoms_to_use.append(atom.GetIdx())
					# Be explicit when there are no hydrogens
					if atom.GetTotalNumHs() == 0:
						symbol = atom.GetSmarts()
						if ':' in symbol: # stick H0 before label
							symbol = symbol.replace(':', ';H0:')
						else: # stick before end
							symbol = symbol.replace(']', ';H0]')
						symbol_replacements.append((atom.GetIdx(), symbol))
						# print('Being explicit about H0!!!!')
					continue

		# Check neighbors (any atom)
		for k in range(radius):
			atoms_to_use, symbol_replacements = expand_atoms_to_use(mol, atoms_to_use, 
				groups = groups, symbol_replacements = symbol_replacements)

		if category == 'products':
			# Add extra labels to include (for products only)
			if expansion:
				for atom in mol.GetAtoms():
					if ':' not in atom.GetSmarts(): continue
					label = atom.GetSmarts().split(':')[1][:-1]
					if label in expansion and label not in changed_atom_tags:
						atoms_to_use.append(atom.GetIdx())
						# Make the expansion a wildcard
						symbol_replacements.append((atom.GetIdx(), convert_atom_to_wildcard(atom)))	
						if v: print('expanded label {} to wildcard in products'.format(label))

		# Define new symbols to replace terminal species with wildcards
		# (don't want to restrict templates too strictly)
		symbols = [atom.GetSmarts() for atom in mol.GetAtoms()]
		for (i, symbol) in symbol_replacements:
			symbols[i] = symbol

		if not atoms_to_use: continue
		# if v:
		# 	print('~~ replacement for this ' + category[:-1])
		# 	print('{} -> {}'.format([mol.GetAtomWithIdx(x).GetSmarts() for (x, s) in symbol_replacements], 
		# 		                    [s for (x, s) in symbol_replacements]))
		fragments += '(' + AllChem.MolFragmentToSmiles(mol, atoms_to_use, 
			atomSymbols = symbols, allHsExplicit = True, allBondsExplicit = True) + ').'
	return fragments[:-1]

def expand_changed_atom_tags(changed_atom_tags, reactant_fragments):
	'''Given a list of changed atom tags (numbers as strings) and a string consisting
	of the reactant_fragments to include in the reaction transform, this function 
	adds any tagged atoms found in the reactant side of the template to the 
	changed_atom_tags list so that those tagged atoms are included in the products'''

	expansion = []
	atom_tags_in_reactant_fragments = re.findall('\:([[0-9]+)\]', reactant_fragments)
	for atom_tag in atom_tags_in_reactant_fragments:
		if atom_tag not in changed_atom_tags:
			expansion.append(atom_tag)
	if v: print('after building reactant fragments, additional labels included: {}'.format(expansion))
	return expansion

def get_special_groups(mol):
	'''Given an RDKit molecule, this function returns a list of tuples, where
	each tuple contains the AtomIdx's for a special group of atoms which should 
	be included in a fragment all together. This should only be done for the 
	reactants, otherwise the products might end up with mapping mismatches'''

	# Define templates, based on Functional_Group_Hierarchy.txt from Greg Laandrum
	group_templates = [ 
		'C(=O)Cl', # acid chloride
		'C(=O)[O;H,-]', # carboxylic acid
		'[$(S-!@[#6])](=O)(=O)(Cl)', # sulfonyl chloride
		'[$(B-!@[#6])](O)(O)', # boronic acid
		'[$(N-!@[#6])](=!@C=!@O)', # isocyanate
		'[N;H0;$(N-[#6]);D2]=[N;D2]=[N;D1]', # azide
		'O=C1N(Br)C(=O)CC1', # NBS brominating agent
		'C=O', # carbonyl
		'ClS(Cl)=O', # thionyl chloride
		]

	# Build list
	groups = []
	for template in group_templates:
		matches = mol.GetSubstructMatches(Chem.MolFromSmarts(template))
		groups.extend(list(matches))
	return groups

def mol_list_to_inchi(mols):
	'''List of RDKit molecules to InChI string separated by ++'''
	inchis = [Chem.MolToInchi(mol) for mol in mols]
	return ' ++ '.join(sorted(inchis))

def mol_list_from_inchi(inchis):
	'''InChI string separated by ++ to list of RDKit molecules'''
	return [Chem.MolFromInchi(inchi.strip()) for inchi in inchis.split('++')]

def canonicalize_template(template):
	'''This function takes one-half of a template SMARTS string 
	(i.e., reactants or products) and re-orders them based on
	an equivalent string without atom mapping.'''

	# Strip labels to get sort orders
	template_nolabels = re.sub('\:[0-9]+\]', ']', template)

	# Split into separate molecules *WITHOUT wrapper parentheses*
	template_nolabels_mols = template_nolabels[1:-1].split(').(')
	template_mols          = template[1:-1].split(').(')

	# Split into fragments within those molecules
	for i in range(len(template_mols)):
		nolabel_mol_frags = template_nolabels_mols[i].split('.')
		mol_frags         = template_mols[i].split('.')

		# Get sort order within molecule, defined WITHOUT labels
		sortorder = [j[0] for j in sorted(enumerate(nolabel_mol_frags), key = lambda x:x[1])]

		# Apply sorting and merge list back into overall mol fragment
		template_nolabels_mols[i] = '.'.join([nolabel_mol_frags[j] for j in sortorder])
		template_mols[i]          = '.'.join([mol_frags[j] for j in sortorder])

	# Get sort order between molecules, defined WITHOUT labels
	sortorder = [j[0] for j in sorted(enumerate(template_nolabels_mols), key = lambda x:x[1])]

	# Apply sorting and merge list back into overall transform
	template = '(' + ').('.join([template_mols[i] for i in sortorder]) + ')'

	return template

def reassign_atom_mapping(transform):
	'''This function takes an atom-mapped reaction and reassigns 
	the atom-mapping labels (numbers) from left to right, once 
	that transform has been canonicalized.'''

	all_labels = re.findall('\:([0-9]+)\]', transform)

	# Define list of replacements which matches all_labels *IN ORDER*
	replacements = []
	replacement_dict = {}
	counter = 1
	for label in all_labels: # keep in order! this is important
		if label not in replacement_dict:
			replacement_dict[label] = str(counter)
			counter += 1
		replacements.append(replacement_dict[label])

	# Perform replacements in order
	transform_newmaps = re.sub('\:[0-9]+\]', 
		lambda match: (':' + replacements.pop(0) + ']'),
		transform)

	return transform_newmaps

def canonicalize_transform(transform):
	'''This function takes an atom-mapped SMARTS transform and
	converts it to a canonical form by, if nececssary, rearranging
	the order of reactant and product templates and reassigning
	atom maps.'''

	transform_reordered = '>>'.join([canonicalize_template(x) for x in transform.split('>>')])
	return reassign_atom_mapping(transform_reordered)

def convert_to_retro(transform):
	'''This function takes a forward synthesis and converts it to a
	retrosynthesis. Only transforms with a single product are kept, since 
	retrosyntheses should have a single reactant (and split it up accordingly).'''
	
	# Split up original transform
	reactants = transform.split('>>')[0]
	products  = transform.split('>>')[1]

	# Don't force products to be from different molecules (?)
	# -> any reaction template can be intramolecular (might remove later)
	products = products[1:-1].replace(').(', '.')

	# Don't force the "products" of a retrosynthesis to be two different molecules!
	reactants = reactants[1:-1].replace(').(', '.')

	return '>>'.join([products, reactants])

def main(db_fpath, N = 15, folder = ''):
	'''Read reactions from Lowe's patent reaction SMILES'''
	global v
	# Open file
	data_fid = open(db_fpath, 'r')

	# Define scoring variables
	total_templates = 0 # total reactions simulated (excludes skipped)
	total_correct = 0 # actual products predicted
	total_precise = 0 # ONLY actual products predicted

	try: # to allow breaking
		# Look for entries
		for i, line in enumerate(data_fid):

			# Are we done?
			if i == N:
				break

			if v: 
				print('##################################')
				print('###        RXN {}'.format(i))
				print('##################################')

			# Unpack
			reaction_smiles = line.split('\t')[0].split(' ')[0] # remove fragment portion, too
			reactants, agents, products = [mols_from_smiles_list(x) for x in 
											[mols.split('.') for mols in reaction_smiles.split('>')]]
			# if 'Mg' in reaction_smiles.split('>')[2]:
			# 	print('Found Mg in product!')
			# 	print(reaction_smiles)
			# 	v = True
			# 	raw_input('Pausing...')
			# else: 
			# 	v = False

			if None in reactants + agents + products: 
				if v: 
					print(reaction_smiles)
					print('Could not parse all molecules in reaction, skipping')
					raw_input('Enter anything to continue...')
				continue

			# Calculate changed atoms
			changed_atoms, changed_atom_tags, err = get_changed_atoms(reactants, products)
			if err: 
				if v: print('skipping')
				continue

			# Draw
			if v: 
				print(reaction_smiles)
				if not os.path.exists('{}/rxn_{}'.format(folder, i)):
					os.makedirs('{}/rxn_{}'.format(folder, i))
				draw_reaction_smiles(reaction_smiles, fpath = '{}/rxn_{}/rxn_{}.png'.format(folder, i, i))

			# Get fragments for reactants
			reactant_fragments = get_fragments_for_changed_atoms(reactants, changed_atom_tags, 
				radius = 1, expansion = [], category = 'reactants')
			# Get fragments for products 
			# (WITHOUT matching groups but WITH the addition of reactant fragments)
			product_fragments  = get_fragments_for_changed_atoms(products, changed_atom_tags, 
				radius = 0, expansion = expand_changed_atom_tags(changed_atom_tags, reactant_fragments),
				category = 'products')

			# Report transform
			rxn_string = '{}>>{}'.format(reactant_fragments, product_fragments)
			if v: print('\nOverall fragment transform: {}'.format(rxn_string))

			# Load into RDKit
			rxn = AllChem.ReactionFromSmarts(rxn_string)
			if rxn.Validate()[1] != 0: continue

			# # Analyze
			# if v: 
			# 	print('Original number of reactants: {}'.format(len(reactants)))
			# 	print('Number of reactants in transform: {}'.format(rxn.GetNumReactantTemplates()))

			# Run reaction
			try:
				# Try all combinations of reactants that fit template
				combinations = itertools.combinations(reactants, rxn.GetNumReactantTemplates())
				unique_product_sets = []
				for combination in combinations:
					outcomes = rxn.RunReactants(list(combination))
					if not outcomes: continue
					#if v: print('\nFor reactants {}'.format([Chem.MolToSmiles(mol) for mol in combination]))
					for j, outcome in enumerate(outcomes):
						#if v: print('- outcome {}/{}'.format(j + 1, len(outcomes)))
						for k, product in enumerate(outcome):
							if v: 
								#print('  - product {}: {}'.format(k, Chem.MolToSmiles(product, isomericSmiles = True)))
								try:
									Chem.SanitizeMol(product)
									product.UpdatePropertyCache()
									#product = Chem.MolFromSmiles(Chem.MolToSmiles(product, isomericSmiles = True))
									Draw.MolToFile(product, '{}/rxn_{}/outcome_{}_product_{}.png'.format(folder, i, j, k), size=(250,250))
								except Exception as e:
									print('warning: could not draw {}: {}'.format(Chem.MolToSmiles(product, isomericSmiles = True), e))
						product_set = mol_list_to_inchi(outcome)
						if product_set not in unique_product_sets:
							unique_product_sets.append(product_set)

				if v: 
					print('\nExpctd {}'.format(mol_list_to_inchi(products)))
					for product_set in unique_product_sets:
						print('Found  {}'.format(product_set))

				if mol_list_to_inchi(products) in unique_product_sets:
					if v: print('\nSuccessfully found true products!')
					total_correct += 1
					if len(unique_product_sets) > 1:
						if v: print('...but also found {} more'.format(len(unique_product_sets) - 1))
					else:
						total_precise += 1

						# Valid reaction!
						rxn_canonical = canonicalize_transform(rxn_string)
						retro_canonical = convert_to_retro(rxn_canonical)

						# Is this old?
						doc = collection.find_one({'reaction_smarts': retro_canonical})

						if doc:
							# Old
							collection.update_one(
								{'_id': doc['_id']},
								{
									'$set': {'count': doc['count'] + 1}
								}

							)
						else:
							# New
							result = collection.insert_one(
								{
									'name': '',
									'reaction_smarts': retro_canonical,
									'rxn_example': reaction_smiles,
									'reference': line.split('\t')[1],
									'explicit_H': False,
									'count': 1,
								}
							)
							#print('Created database entry {}'.format(result.inserted_id))

				else:
					if v: print('\nDid not find true products')
					if len(unique_product_sets) > 1:
						if v: print('...but found {} unexpected ones'.format(len(unique_product_sets)))
				
				total_templates += 1
				if v: 
					draw_reaction_smiles(rxn_string, fpath = '{}/rxn_{}/tform_{}.png'.format(folder, i, i))
					with open('{}/rxn_{}/tform_{}.txt'.format(folder, i, i), 'w') as tform_fid:
						tform_fid.write(rxn_string)
			
			except Exception as e:
				if v: 
					print(e)
					print('skipping')
					raw_input('Enter anything to continue')
				continue


			# Report progress
			if (i % 1000) == 0:
				print('{}/{}'.format(i, N))

			# Pause
			if v: raw_input('Enter anything to continue...')

	except KeyboardInterrupt:
		print('Stopped early!')		
	except Exception as e:
		print(e)

	print('...finished looking through {} reaction records'.format(min([N, i])))

	print('Correct product predictions in {}/{} ({}%) cases'.format(total_correct, 
		total_templates, total_correct * 100.0 / total_templates))
	print('Specific product predictions in {}/{} ({}%) cases'.format(total_precise, 
		total_templates, total_precise * 100.0 / total_templates))
	print('Created {} database entries'.format(collection.find().count()))

	return True


if __name__ == '__main__':

	parser = argparse.ArgumentParser()
	parser.add_argument('data_file', type = str, 
		 				help = 'File where each line is an atom-mapped smiles reaction')
	parser.add_argument('-v', type = bool, default = False,
						help = 'Verbose printing (incl. saving images); defaults to False')
	parser.add_argument('-o', '--out', type = str, default = '',
						help = 'Folder to output images to if verbose')
	parser.add_argument('-n', '--num', type = int, default = 50,
						help = 'Maximum number of records to examine; defaults to 50')
	args = parser.parse_args()

	v = args.v
	lg = RDLogger.logger()
	if not v: lg.setLevel(4)

	clear = raw_input('Do you want to clear the {} existing templates? '.format(collection.find().count()))
	if clear in ['y', 'Y', 'yes', '1', 'Yes']:
		result = collection.delete_many({})
		print('Cleared {} entries from collection'.format(result.deleted_count))

	main(args.data_file, N = args.num, folder = args.out)