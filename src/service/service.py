import cherrypy
from src.solver.minisat import MiniSATAdapter

"""
class Parser(object):
    exposed = True

    def __init__(self,parser):
        self._parser = parser

    def POST(self,policy):
        #return self._parser.parse(policy)
        return policy
"""

class Aggregator(object):
    import ast
    from src.parser.iptables import IP6TablesAdapter

    exposed = True


    def POST(self,firewalls=None,networks=None):
        import lxml.etree as et
        return networks # TODO

        config = et.Element('config')
        if firewalls is not None:
            firewalls = ast.literal_eval(firewalls)
            fwconfigs = []
            for firewall in firewalls:
                fwconfigs.append(IP6TablesAdapter.parse(firewall))
            firewalls = et.Element('firewalls')
            firewalls.extend(fwconfigs)
            config.append(firewalls)
        if networks is not None:
            config.append(et.fromstring(networks))
        return et.tostring(config)


class Instantiator(object):

    exposed = True

    def POST(self,config,anomalies=1):
        import lxml.etree as et
        from src.core.instantiator import Instantiator as inst
        from src.xml.xmlutils import XMLUtils

        anomalies = int(anomalies)

        REACH = 1
        CYCLE = 2
        SHADOW= 4
        CROSS = 8

        reach = (anomalies & REACH) != 0
        cycle = (anomalies & CYCLE) != 0
        shadow = (anomalies & SHADOW) != 0
        cross = (anomalies & CROSS) != 0

        config = et.fromstring(config)
        XMLUtils.deannotate(config)
        instances = inst.instantiate(config,reach,cycle,shadow,cross)
        instances = { instance:et.tostring(instances[instance]) for instance in instances }
        return str(instances)


class Solver(object):
    exposed = True

    def __init__(self,solver):
        self._solver = solver

    def POST(self,instances):
        import ast
        import lxml.etree as et
        instances = ast.literal_eval(instances)
        results = { instance : self._solver.solve(et.fromstring(instances[instance])) for instance in instances }

        return str(results)


class Root(object):
    exposed = True

    def __init__(self):
        self._index = '/index.html'


    def GET(self):
        raise cherrypy.HTTPRedirect(self._index)


class Service:
    def start(self):
        cherrypy.config.update(self._globconf)
        cherrypy.config.update(self._appconf)
        cherrypy.tree.mount(self._root,'/',self._appconf)
        cherrypy.tree.mount(self._aggregator,'/aggregator',self._appconf)
        cherrypy.tree.mount(self._instantiator,'/instantiator',self._appconf)
        #cherrypy.tree.mount(self._parser,'/parser',self._appconf)
        cherrypy.tree.mount(self._solver,'/solver',self._appconf)
        cherrypy.engine.start()
        cherrypy.engine.block()

    def __init__(self):
        self._root = Root()
        self._aggregator = Aggregator()
        self._instantiator = Instantiator()
        #self._parser = Parser()
        self._solver = Solver(MiniSATAdapter())

        self._globconf = './src/service/global.conf'
        self._appconf = './src/service/app.conf'

if __name__ == '__main__':
    service = Service()
    service.start()
