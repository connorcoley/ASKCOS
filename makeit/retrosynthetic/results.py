import rdkit.Chem as Chem
from rdkit.Chem import AllChem
import makeit.global_config as gc


class RetroResult:
    """A class to store the results of a one-step retrosynthesis.

    Attributes:
        target_smiles (str): SMILES string of target molecule.
        precursors (list of RetroPrecursor): Precursors of the target.
        smiles_list_to_precursor (dict): Maps SMILES string of precursor(s) to
            its index in the precursors list.
    """

    def __init__(self, target_smiles):
        """Initializes RetroResult.

        Args:
            target_smiles (str): SMILES string of target molecule.
        """
        self.target_smiles = target_smiles
        self.precursors = []
        self.smiles_list_to_precursor = {}

    def add_precursor(self, precursor, prioritizer, **kwargs):
        """Adds precursor to retrosynthesis result if it is a new and unique.

        Updates precursor stats if not new.

        Args:
            precursor (RetroPrecursor): Precursor to be added.
            prioritizer (Prioritizer): Prioritizer used to score this
                precursor.
            **kwargs: Additional optional arguments. Used for mode.
        """
        try:
            index = self.smiles_list_to_precursor[
                '.'.join(precursor.smiles_list)]
        except KeyError:
            # If neither has been encountered: add new product
            precursor.prioritize(prioritizer, mode=kwargs.get('mode', gc.max))
            self.precursors.append(precursor)
            self.smiles_list_to_precursor['.'.join(precursor.smiles_list)] = len(self.precursors) - 1
            return

        self.precursors[index].template_ids |= set(precursor.template_ids)
        self.precursors[index].num_examples += precursor.num_examples
        if self.precursors[index].template_score < precursor.template_score:
            self.precursors[index].template_score = precursor.template_score

    def return_top(self, n=50):
        """Returns the top n precursors as a list of dictionaries.

        Output is sorted by descending score.

        Args:
            n (int, optional) Number of precursors to return. (default: {50})
        """
        top = []
        for (i, precursor) in enumerate(sorted(self.precursors,
                                               key=lambda x: x.retroscore, reverse=True)):
            # Casts to float are necessary to maintain JSON serializability
            # when using celery
            top.append({
                'rank': i + 1,
                'smiles': '.'.join(precursor.smiles_list),
                'smiles_split': precursor.smiles_list,
                'score': float(precursor.retroscore),
                'num_examples': precursor.num_examples,
                'tforms': sorted(list(precursor.template_ids)),
                'template_score': float(precursor.template_score),
                'necessary_reagent': precursor.necessary_reagent,
                'plausibility': precursor.plausibility,
            })
            if i + 1 == n:
                break
        return top


class RetroPrecursor:
    """A class to store a single set of precursor(s) for a retrosynthesis.

    Does NOT contain the target molecule information.

    Attributes:
        retroscore (float): Prioritization score of this precursor.
        num_examples (int): Number of the precursor's templates appear.
        smiles_list (list of str): SMILES strings of the precursor.
        template_ids (set of str): IDs of the templates used to find this
            precursor.
        template_score (float): Maximum prioritization score of the templates
            used for this precursor.
        necessary_reagent (str): SMILES string of any reagents necessary for the
            reation.
        plausibility (float): Plausibility assigned to successful reaction.
    """

    def __init__(self, smiles_list=[], template_id=-1, template_score=1, num_examples=0, necessary_reagent='', plausibility=1.0):
        """Initializes RetroPrecursor.

        Args:
            smiles_list (list of str, optional): SMILES strings of the
                precursor. (default: {[]})
            template_id (int or str, optional): IDs of the templates used to
                find this precursor. (default: {-1})
            template_score (float, optional): Maximum prioritization score of
                the templates used for this precursor. (default: {1})
            num_examples (int, optional): Number of the precursor's templates
                appear. (default: {0})
            necessary_reagent (str, optional): SMILES string of any reagents
                necessary for the reation. (default: {''})
            plausibility (float, optional): Plausibility assigned to successful
                reaction. (default: {1.0})
        """
        self.retroscore = 0
        self.num_examples = num_examples
        self.smiles_list = smiles_list
        self.template_ids = set([template_id])
        self.template_score = template_score
        self.necessary_reagent = necessary_reagent
        self.plausibility = plausibility

    def prioritize(self, prioritizer, mode=gc.max):
        """Calculates priority score of this precursor.

        Calculates the score of this step as the worst of all precursors,
        plus some penalty for a large necessary_reagent.

        Args:
            prioritizer (Prioritizer): Prioritizer used to score this
                precursor.
            mode (str, optional): Specifies function to use to merge list of
                scores in prioritizer. (default: {gc.max})
        """
        self.retroscore = prioritizer.get_priority(self, mode=mode)
