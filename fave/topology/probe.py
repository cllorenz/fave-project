import json
import itertools

from util.packet_util import ETHER_TYPE_IPV6, normalize_ipv6_address, normalize_ipv6_proto, normalize_upper_port
from util.path_util import Path
from util.match_util import oxm_field_to_match_field
from netplumber.mapping import Mapping,FIELD_SIZES
from netplumber.vector import set_field_in_vector, Vector, HeaderSpace
from ip6np.generator import field_value_to_bitvector
from ip6np.packet_filter import Field

class ProbeModel(object):
    def __init__(self,node,quantor,filter_expr={},test_expr={}):
        self.node = node
        self.type = "probe"
        self.ports = { node+'_1' : 1 }
        self.quantor = quantor
        self.mapping = Mapping()

        filter_fields = []
        test_fields = []

        if not filter_expr:
            filter_expr = {'filter_fields':{}}
        if not test_expr:
            test_expr = {'test_fields':{},'test_path':[]}

        for vectors,fields in [
            (filter_fields,filter_expr['filter_fields']),
            (test_fields,test_expr['test_fields'])
        ]:
            for field in fields:
                self.mapping.extend(oxm_field_to_match_field[field])

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
                            Field(field,FIELD_SIZES[field],comb[i])
                        ).vector
                    )
                vectors.append(vector)

        self.filter_fields = HeaderSpace(self.mapping.length,filter_fields)
        self.test_fields = HeaderSpace(self.mapping.length,test_fields)

        self.test_path = Path(test_expr['test_path'])


    def to_json(self):
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
        if type(j) == str:
            j = json.loads(j)

        model = ProbeModel(
            j["node"],
            j["quantor"],
        )
        model.test_path=Path.from_json(j["test_path"])
        model.mapping = Mapping.from_json(j["mapping"])
        model.filter_fields = HeaderSpace.from_json(j["filter_fields"])
        model.test_fields = HeaderSpace.from_json(j["test_fields"])

        return model
