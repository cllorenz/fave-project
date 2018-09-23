""" This module provides a probe model.
"""

import json
import itertools

from util.path_util import Path
from util.match_util import OXM_FIELD_TO_MATCH_FIELD
from netplumber.mapping import Mapping
from netplumber.vector import set_field_in_vector, Vector, HeaderSpace
from ip6np.ip6np_util import field_value_to_bitvector
from openflow.switch import SwitchRuleField

class ProbeModel(object):
    """ This class provides a probe model.
    """

    def __init__(self, node, quantor, filter_expr=None, test_expr=None):
        self.node = node
        self.type = "probe"
        self.ports = {node+'_1' : 1}
        self.quantor = quantor
        self.mapping = Mapping()

        filter_fields = []
        test_fields = []

        if filter_expr is None:
            filter_expr = {'filter_fields':{}}
        if test_expr is None:
            test_expr = {'test_fields':{}, 'test_path':[]}

        for vectors, fields in [
                (filter_fields, filter_expr['filter_fields']),
                (test_fields, test_expr['test_fields'])
        ]:
            for field in fields:
                self.mapping.extend(OXM_FIELD_TO_MATCH_FIELD[field])

            keys = sorted(fields)
            combinations = itertools.product(*(fields[k] for k in keys))

            for comb in combinations:
                vector = Vector(self.mapping.length)
                for idx, oxm in enumerate(keys):
                    field = OXM_FIELD_TO_MATCH_FIELD[oxm]
                    set_field_in_vector(
                        self.mapping,
                        vector,
                        field,
                        field_value_to_bitvector(
                            SwitchRuleField(field, comb[idx])
                        ).vector
                    )
                vectors.append(vector)

        self.filter_fields = HeaderSpace(self.mapping.length, filter_fields)
        self.test_fields = HeaderSpace(self.mapping.length, test_fields)

        self.test_path = Path(test_expr['test_path'])


    def to_json(self):
        """ Converts the probe to JSON.
        """

        return {
            "node" : self.node,
            "type" : self.type,
            "quantor" : self.quantor,
            "mapping" : self.mapping.to_json(),
            "filter_fields" : self.filter_fields.to_json(),
            "test_fields" : self.test_fields.to_json(),
            "test_path" : self.test_path.to_json()
        }

    @staticmethod
    def from_json(j):
        """ Creates a probe from JSON.

        Keyword arguments:
        j -- a JSON string or object
        """

        if isinstance(j, str):
            j = json.loads(j)

        model = ProbeModel(
            j["node"],
            j["quantor"]
        )
        model.test_path = Path.from_json(j["test_path"])
        model.mapping = Mapping.from_json(j["mapping"])
        model.filter_fields = HeaderSpace.from_json(j["filter_fields"])
        model.test_fields = HeaderSpace.from_json(j["test_fields"])

        return model
