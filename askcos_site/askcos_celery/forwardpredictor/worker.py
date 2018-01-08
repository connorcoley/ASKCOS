'''
The role of a forward predictor worker is to apply a subset of 
templates and generate candidate edits
'''

from __future__ import absolute_import, unicode_literals, print_function
from celery import shared_task
from celery.signals import celeryd_init
import time
from rdkit import RDLogger
lg = RDLogger.logger()
lg.setLevel(RDLogger.CRITICAL)

CORRESPONDING_QUEUE = 'fp_worker'
templates = None

@celeryd_init.connect
def configure_worker(options={},**kwargs):
    if 'queues' not in options: 
        return 
    if CORRESPONDING_QUEUE not in options['queues'].split(','):
        return
    print('### STARTING UP A FORWARD PREDICTOR WORKER ###')

    global templates
    
    # Get Django settings
    from django.conf import settings

    # Database
    from database import db_client
    db = db_client[settings.SYNTH_TRANSFORMS['database']]
    SYNTH_DB = db[settings.SYNTH_TRANSFORMS['collection']]

    # Rdkit
    import rdkit.Chem as Chem 
    from makeit.predict.summarize_reaction_outcome import summarize_reaction_outcome

    # Load templates
    from .common import load_templates
    mincount_synth = settings.SYNTH_TRANSFORMS['mincount']
    templates = load_templates(SYNTH_DB=SYNTH_DB, mincount=mincount_synth)
    print('Finished initializing forward predictor worker')

@shared_task
def get_candidate_edits(reactants_smiles, start_at, end_at):
    '''Apply forward templates to a atom-mapped reactant pool. We
    use chunks (start_at, end_at) to have fewer queue messages

    reactants_smiles = SMILES of reactants (atom-mapped)
    start_at = index of templates to start at
    end_at = index of templates to end at'''

    global templates
    
    import rdkit.Chem as Chem 
    from makeit.predict.summarize_reaction_outcome import summarize_reaction_outcome

    # print('Forward predictor worker was asked to expand {} ({}->{})'.format(reactants_smiles, start_at, end_at))
    reactants = Chem.MolFromSmiles(reactants_smiles)

    candidate_list = []
    for i in range(start_at, end_at):
        try:

            outcomes = templates[i]['rxn_f'].RunReactants([reactants])
            if templates[i]['reaction_smarts'] == str('[#8]=[C;H0;+0:1](-[*:2])-[OH;+0:3].[*:4]-[OH;+0:5]>>[*:2]-[C;H0;+0:1](=[O;H0;+0:3])-[O;H0;+0:5]-[*:4]'):
                print(outcomes)
            if not outcomes: continue # no match

            for j, outcome in enumerate(outcomes):
                outcome = outcome[0] # all products represented as single mol by transforms

                try:
                    outcome.UpdatePropertyCache()
                    Chem.SanitizeMol(outcome)
                    [a.SetProp(str('molAtomMapNumber'), a.GetProp(str('old_molAtomMapNumber'))) \
                        for a in outcome.GetAtoms() \
                        if str('old_molAtomMapNumber') in a.GetPropsAsDict()]
                
                    # Reduce to largest (longest) product only
                    candidate_smiles = Chem.MolToSmiles(outcome, isomericSmiles=True)
                    candidate_smiles = max(candidate_smiles.split('.'), key=len)
                    outcome = Chem.MolFromSmiles(candidate_smiles)
                        
                    # Find what edits were made
                    edits = summarize_reaction_outcome(reactants, outcome)

                    # Remove mapping before matching
                    [x.ClearProp(str('molAtomMapNumber')) for x in outcome.GetAtoms() \
                        if x.HasProp(str('molAtomMapNumber'))] # remove atom mapping from outcome

                    # Overwrite candidate_smiles without atom mapping numbers
                    candidate_smiles = Chem.MolToSmiles(outcome, isomericSmiles=True)

                    # Add to ongoing list
                    candidate_list.append((candidate_smiles, edits))
                except Exception as e: # other RDKit error?
                    # print(e) # fail quietly
                    # print(Chem.MolToSmiles(outcome))
                    # print(templates[i]['reaction_smarts'])
                    # print(templates[i]['_id'])
                    continue
        except IndexError: # out of range w/ templates
            print('INDEX ERROR!')
            break 
        except Exception as e: # other RDKit error?
            print(e)
            continue    

    #print('Returning {} candidates'.format(len(candidate_list)))
    return candidate_list