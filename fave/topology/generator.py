import json
import itertools

from netplumber.mapping import Mapping, field_sizes
from netplumber.vector import set_field_in_vector, Vector, HeaderSpace
from ip6np.generator import field_value_to_bitvector
from ip6np.packet_filter import Field
from util.match_util import oxm_field_to_match_field

class GeneratorModel(object):
    def __init__(self,node,fields={}):
        self.node = node
        self.type = "generator"
        self.ports = { node+'_1' : 1 }

        self.mapping = Mapping()

        for field in fields:
            self.mapping.extend(oxm_field_to_match_field[field])

        outgoing = []

        keys = sorted(fields)
        combinations = itertools.product(*(fields[k] for k in keys))

        for comb in combinations:
            vector = Vector(self.mapping.length)
            for i,oxm in enumerate(keys):
                field = oxm_field_to_match_field[oxm]
                set_field_in_vector(
                    self.mapping,
                    vector,
                    field,
                    field_value_to_bitvector(
                        Field(field,field_sizes[field],comb[i])
                    ).vector
                )
            outgoing.append(vector)

        self.outgoing = HeaderSpace(self.mapping.length,outgoing)


    def to_json(self):
        return {
            "node" : self.node,
            "type" : self.type,
            "mapping" : self.mapping.to_json(),
            "outgoing" : self.outgoing.to_json()
        }

    @staticmethod
    def from_json(j):
        if type(j) == str:
            j = json.loads(j)

        model = GeneratorModel(
            j["node"],
        )
        model.mapping = Mapping.from_json(j["mapping"])
        model.outgoing = HeaderSpace.from_json(j["outgoing"])

        return model
