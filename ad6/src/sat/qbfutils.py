#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2015 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

import lxml.etree as et
from copy import deepcopy
from functools import reduce

class QBFUtils:
    def markUnbound(formula,bound):
        newbound = bound
        if formula.tag == 'variable' and not formula.attrib['name'] in bound:
            formula.attrib['name'] += '_f'

        if formula.tag in ['exists','forall']:
            newbound += [formula.attrib['variable']]
        for subformula in formula:
            QBFUtils.markUnbound(subformula,newbound)


    def unifyVariables(formula,index):
        newindex = index
        if formula.tag in ['exists','forall']:
            newindex += 1

        for subformula in formula:
            QBFUtils.unifyVariables(subformula,newindex)

        if formula.tag in ['exists','forall']:
            for variable in filter(lambda x: x.attrib['name'] == formula.attrib['variable'],formula.iterfind('.//variable')):
                variable.attrib['name'] += '_'+str(index)
            formula.attrib['variable'] += '_'+str(index)


    def convertToPrenex(formula):
        repeat = False
        for subformula in formula:
            QBFUtils.convertToPrenex(subformula)

        if formula.tag in ['variable','constant','exists','forall']:
            return

        if formula.tag in ['conjunction','disjunction']:
            for subformula in formula:
                if subformula.tag in ['exists','forall']:
                    parent = formula.getparent()
                    quantor = subformula
                    subformula = quantor[0]
                    quantor.remove(subformula)
                    formula.replace(quantor,subformula)
                    parent.replace(formula,quantor)
                    quantor.append(formula)
            return

        quantor = None
        subformula = None
        parent = formula.getparent()

        if formula.tag == 'negation':
            if formula[0].tag in ['exists','forall']:
                quantor = formula[0]
                subformula = quantor[0]
                quantor.tag = 'exists' if quantor.tag == 'forall' else 'forall'

        if formula.tag == 'equality':
            first = ''
            second = ''
            if formula[0].tag == 'exists':
                first = 'forall'
                second = 'exists'
                quantor = formula[0]
            elif formula[0].tag == 'forall':
                first = 'exists'
                second = 'forall'
                quantor = formula[0]
            elif formula[1].tag == 'exists':
                first = 'exists'
                second = 'forall'
                quantor = formula[1]
            elif formula[1].tag == 'forall':
                first = 'forall'
                second = 'exists'
                quantor = formula[1]
            else:
                return
            subformula = quantor[0]
            quantor.remove(subformula)
            formula.replace(quantor,subformula)
            quantor.tag = second
            quantor.append(deepcopy(quantor))
            quantor.tag = first
            parent.replace(formula,quantor)
            quantor[0].append(formula)
            QBFUtils.convertToPrenex(formula)
            return


        if formula.tag == 'implication':
            repeat = True
            if formula[0].tag in ['exists','forall']:
                quantor = formula[0]
                subformula = quantor[0]
                quantor.tag = 'exists' if quantor.tag == 'forall' else 'forall'
            elif formula[1].tag in ['exists','forall']:
                quantor = formula[1]
                subformula = quantor[0]
            else:
                return

        quantor.remove(subformula)
        formula.replace(quantor,subformula)
        parent.replace(formula,quantor)
        quantor.append(formula)
        if repeat:
            QBFUtils.convertToPrenex(formula)

    def convertQBFToPrenex(formula):
        QBFUtils.markUnbound(formula,[])
        QBFUtils.unifyVariables(formula,0)
        for variable in filter(lambda x: x.attrib['name'].endswith('_f'),formula.iterfind('variable')):
            variable.attrib['name'] = variable.attrib['name'].rstrip('_f')
        QBFUtils.convertToPrenex(formula)

    # returns { varname : [variables] }
    def getPrefixes(prenex):
        prefix = []
        prefixes = {}
        formula = prenex
        while formula.tag in ['exists','forall']:
            if formula.tag == 'forall':
                prefix.append(formula.attrib['variable'])
            if formula.tag == 'exists':
                prefixes[formula.attrib['variable']] = deepcopy(prefix)

            formula = formula[0]
        return prefixes


    def replacePrefix(formula,prefix):
        variable = prefix[0]
        prefixlist = prefix[1]
        variablelist = list(map(lambda x: et.Element('variable',{'name' : x}),prefixlist))
        function = et.Element('function')
        function.attrib['name'] = variable
        function.extend(variablelist)

        variables = formula.iterfind('.//variable[@name="' + variable + '"]')
        for var in variables:
            parent = var.getparent()
            try:
                neg = var.attrib['negated']
                if neg == 'true':
                    tmp = et.Element('negation')
                    tmp.append(function)
                    parent.replace(var,tmp)
                else:
                    parent.replace(var,function)
            except KeyError:
                parent.replace(var,function)

        quantors = formula.iterfind('.//exists')
        for quantor in quantors:
            parent = quantor.getparent()
            parent.replace(quantor,quantor[0])

    # warning: exponential time complexity with the number of function variables
    # returns tuple (function name, constraint)
    def buildSkolemConstraint(function):
        fname = 'skolem_'+function.attrib['name']
        variables = list(function)
        if len(variables) > 0:
            conjunction = et.Element('conjunction')
        else:
            raise Exception('Error while building skolem constraint: function without arguments')

        for i in range(2**len(variables)):
            impl = et.Element('implication')
            conj = et.Element('conjunction')
            fvarname = fname
            for variable in variables:
                bln = bool(i & 0x1)
                variable.attrib['negated'] = 'false' if bln else 'true'
                conj.append(deepcopy(variable))
                fvarname += '_' + variable.attrib['name'] + ':' + str(bln)
                i >>= 1
            impl.extend([conj,et.Element('variable',{'name':fvarname})])
            conjunction.append(impl)

        return (fname,conjunction)


    def buildSkolemConstraints(functions):
        constraints = {}
        for function in functions:
            constraint = QBFUtils.buildSkolemConstraint(function)
            constraint[constraint[0]] = constraint[1]
        return constraints


    # returns dictionary of Skolem constraints and replaces Skolem functions in the formula
    def replaceSkolemFunctions(formula):
        constraints = {}
        functions = formula.iterfind('.//function')
        for function in functions:
            parent = function.getparent()
            constraint = QBFUtils.buildSkolemConstraint(function)
            fvarname = constraint[0]
            fvar = et.Element('variable',{'name':fvarname})
            parent.replace(function,fvar)
            constraints[fvarname] = constraint[1]
        return constraints


    def convertPrenexToSkolem(formula):
        prefixes = QBFUtils.getPrefixes(formula)
        for prefix in prefixes:
            QBFUtils.replacePrefix(formula,(prefix,prefixes[prefix]))
        return
        constraints = QBFUtils.replaceSkolemFunctions(formula)
        for const in constraints:
            print(const)
            et.dump(constraints[const])
