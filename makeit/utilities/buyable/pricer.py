import makeit.global_config as gc
import rdkit.Chem as Chem
from collections import defaultdict
from tqdm import tqdm
from makeit.utilities.io.logging import MyLogger
import cPickle as pickle
from pymongo import MongoClient
from multiprocessing import Manager
import os
pricer_loc = 'pricer'


class Pricer:
    '''
    The Pricer class is used to look up the ppg of chemicals if they
    are buyable.
    '''

    def __init__(self, by_xrn=False, done=None, BUYABLES=None, CHEMICALS=None):

        self.CHEMICAL_DB = CHEMICALS
        self.BUYABLE_DB = BUYABLES
        self.by_xrn = False
        self.done = done
        self.prices = defaultdict(float)  # default 0 ppg means not buyable
        # default 0 ppg means not buyable
        self.prices_flat = defaultdict(float)
        self.prices_by_xrn = defaultdict(float)

    def load_databases(self):
        '''
        Load the pricing data from the online database
        '''
        db_client = MongoClient(gc.MONGO['path'], gc.MONGO[
                                'id'], connect=gc.MONGO['connect'])
        db = db_client[gc.BUYABLES['database']]
        self.BUYABLE_DB = db[gc.BUYABLES['collection']]
        db = db_client[gc.CHEMICALS['database']]
        self.CHEMICAL_DB = db[gc.CHEMICALS['collection']]

    def dump_to_file(self, file_path=gc.pricer_data):
        '''
        Write the data from the online datbases to a local file
        '''
        if not (self.BUYABLE_DB and self.CHEMICAL_DB):
            MyLogger.print_and_log(
                "No database information to output to file.", pricer_loc, level=3)
            return

        with open(file_path, 'wb') as file:
            pickle.dump(self.prices, file, gc.protocol)
            pickle.dump(self.prices_flat, file, gc.protocol)
            pickle.dump(self.prices_by_xrn, file, gc.protocol)

    def load_from_file(self, file_path=gc.pricer_data):
        '''
        Load the data for the pricer from a locally stored file instead of from the online database.
        '''
        if os.path.isfile(file_path):
            with open(file_path, 'rb') as file:
                self.prices = pickle.load(file)
                self.prices_flat = pickle.load(file)
                self.prices_by_xrn = pickle.load(file)
        else:
            self.load_databases()
            self.load()
            self.dump_to_file()

    def load(self, online=True, CHEMICAL_DB=None, BUYABLE_DB=None, max_ppg=1e10):
        '''
        Loads the object from a MongoDB collection containing transform
        template records.
        '''
        MyLogger.print_and_log(
            'Loading pricer with buyable limit of ${} per gram.'.format(max_ppg), pricer_loc)
        # Save collection source use online option to load either from local
        # file or from online database.
        self.prices = defaultdict(float)  # default 0 ppg means not buyable
        # default 0 ppg means not buyable
        self.prices_flat = defaultdict(float)
        self.prices_by_xrn = defaultdict(float)

        if self.BUYABLE_DB and self.CHEMICAL_DB:
            pass
        elif not (CHEMICAL_DB and BUYABLE_DB):
            if online:
                self.load_databases()
            else:
                self.load_from_file()
        else:
            self.CHEMICAL_DB = CHEMICAL_DB
            self.BUYABLE_DB = BUYABLE_DB

        buyable_dict = {}
        # First pull buyables source (smaller)
        for buyable_doc in self.BUYABLE_DB.find({'source': {'$ne': 'LN'}}, 
                        ['ppg', 'smiles', 'smiles_flat'],
                        no_cursor_timeout=True):
            # smiles = buyable_doc['smiles']
            # smiles_flat = buyable_doc['smiles_flat']

            if buyable_doc['ppg'] > max_ppg:
                continue

            # Deal with multi-species ones (pretty common):
            for smiles in buyable_doc['smiles'].split('.'):

                if self.prices[smiles]:  # already in dict as non-zero, so keep cheaper
                    self.prices[smiles] = min(
                        buyable_doc['ppg'], self.prices[smiles])
                else:
                    self.prices[smiles] = buyable_doc['ppg']

            for smiles_flat in buyable_doc['smiles_flat'].split('.'):
                if self.prices_flat[smiles_flat]:
                    self.prices_flat[smiles_flat] = min(
                        buyable_doc['ppg'], self.prices_flat[smiles_flat])
                else:
                    self.prices_flat[smiles_flat] = buyable_doc['ppg']

        if self.by_xrn:
            # Then pull chemicals source for XRNs (larger)
            for chemical_doc in tqdm(self.CHEMICAL_DB.find({'buyable_id': {'$gt': -1}}, ['buyable_id'], no_cursor_timeout=True)):
                if 'buyable_id' not in chemical_doc:
                    continue
                self.prices_by_xrn[chemical_doc['_id']] = buyable_dict[
                    chemical_doc['buyable_id']]

        MyLogger.print_and_log('Pricer has been loaded.', pricer_loc)

        # multiprocessing notify done
        if self.done == None:
            pass
        else:
            self.done.value = 1

    def lookup_smiles(self, smiles, alreadyCanonical=False, isomericSmiles=True):
        '''
        Looks up a price by SMILES. Tries it as-entered and then 
        re-canonicalizes it in RDKit unl ess the user specifies that
        the string is definitely already canonical.
        '''
        ppg = self.prices_flat[smiles]
        if ppg:
            return ppg

        ppg = self.prices[smiles]
        if ppg:
            return ppg

        if not alreadyCanonical:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return 0.
            smiles = Chem.MolToSmiles(mol, isomericSmiles=isomericSmiles)

            ppg = self.prices_flat[smiles]
            if ppg:
                return ppg

            ppg = self.prices[smiles]
            if ppg:
                return ppg

        return ppg

    def lookup_xrn(self, xrn):
        '''
        Looks up a price by Reaxys XRN.
        '''
        if not self.by_rxn:
            raise ValueError('Not initialized to look up prices by XRN!')
        return self.prices_by_xrn[xrn]
