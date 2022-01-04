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

from copy import deepcopy
from src.xml.xmlutils import XMLUtils

class SATUtils:
    _CLAUSE = "clause"
    SUB = "sub"

    def _ResolveConstants(Formula):
        for SubFormula in Formula:
            SATUtils._ResolveConstants(SubFormula)

        Parent = Formula.getparent()
        if Parent is None:
            return

        if Formula.tag == XMLUtils.NEGATION:
            Child = Formula[0]
            if Child.tag == XMLUtils.CONSTANT:
                Flag = Child.attrib[XMLUtils.ATTRVALUE] == 'true'
                Child.attrib[XMLUtils.ATTRVALUE] = 'false' if Flag else 'true'
                Formula.remove(Child)
                Parent.replace(Formula,Child)

        if Formula.tag == XMLUtils.IMPLICATION:
            Implicant,Conclusio = Formula
            if Implicant.tag == XMLUtils.CONSTANT:
                if Implicant.attrib[XMLUtils.ATTRVALUE] == 'true':
                    Formula.remove(Conclusio)
                    Parent.replace(Formula,Conclusio)
                else:
                    Parent.replace(Formula,XMLUtils.constant())

            elif Conclusio.tag == XMLUtils.CONSTANT:
                if Conclusio.attrib[XMLUtils.ATTRVALUE] == 'true':
                    Parent.replace(Formula,XMLUtils.constant())
                else:
                    Formula.remove(Implicant)
                    Negation = SATUtils._Negate(Implicant)
                    Parent.replace(Formula,Negation)
            else:
                Formula.remove(Implicant)
                Negation = SATUtils._Negate(Implicant)
                Formula.append(Negation)
                Formula.tag = XMLUtils.DISJUNCTION

        elif Formula.tag == XMLUtils.EQUALITY:
            Sub1,Sub2 = Formula
            if Sub1.tag == XMLUtils.CONSTANT:
                if Sub1.attrib[XMLUtils.ATTRVALUE] == 'true':
                    Formula.remove(Sub2)
                    Parent.replace(Formula,Sub2)
                else:
                    Formula.remove(Sub2)
                    Negation = SATUtils._Negate(Sub2)
                    Parent.replace(Formula,Negation)

            elif Sub2.tag == XMLUtils.CONSTANT:
                if Sub2.attrib[XMLUtils.ATTRVALUE] == 'true':
                    Formula.remove(Sub1)
                    Parent.replace(Formula,Sub1)
                else:
                    Formula.remove(Sub1)
                    Negation = SATUtils._Negate(Sub1)
                    Parent.replace(Formula,Negation)

            else:
                Conjunction = XMLUtils.conjunction()
                Disj1 = XMLUtils.disjunction()
                Disj2 = XMLUtils.disjunction()

                Formula.remove(Sub1)
                Formula.remove(Sub2)

                Neg1 = SATUtils._Negate(deepcopy(Sub1))
                Disj1.extend([Neg1,deepcopy(Sub2)])

                Neg2 = SATUtils._Negate(Sub2)
                Disj2.extend([Sub1,Neg2])

                Conjunction.extend([Disj1,Disj2])
                Parent.replace(Formula,Conjunction)

        elif Formula.tag == XMLUtils.CONJUNCTION:
            if any(map(lambda x: SATUtils._IsFalseConstant(x), list(Formula))):
                Parent.replace(Formula,XMLUtils.constant(False))
                return

            Trues = [Elem for Elem in list(Formula) if SATUtils._IsTrueConstant(Elem)]
            for Constant in Trues:
                Formula.remove(Constant)

            if len(Formula) == 1:
                Child = Formula[0]
                Parent.replace(Formula,Child)
            elif len(Formula) == 0:
                Parent.replace(Formula,XMLUtils.constant())

        elif Formula.tag == XMLUtils.DISJUNCTION:
            if any(map(lambda x: SATUtils._IsTrueConstant(x), list(Formula))):
                Parent.replace(Formula,XMLUtils.constant())
                return

            Falses = [Elem for Elem in list(Formula) if SATUtils._IsFalseConstant(Elem)]
            for Constant in Falses:
                Formula.remove(Constant)

            if len(Formula) == 1:
                Child = Formula[0]
                Formula.remove(Child)
                Parent.replace(Formula,Child)
            elif len(Formula) == 0:
                Parent.replace(Formula,XMLUtils.constant(False))


    def _ReduceToDNC(Formula):
        SATUtils._ResolveConstants(Formula)


    # negate Formula
    def _Negate(Formula):
        if Formula.tag == XMLUtils.CONSTANT: # handle constants
            Flag = Formula.get(XMLUtils.ATTRVALUE) == 'true'
            Formula.attrib[XMLUtils.ATTRVALUE] = 'false' if Flag else 'true'
            return Formula
        if Formula.tag == XMLUtils.VARIABLE: # handle Variables
            Flag = Formula.get(XMLUtils.ATTRNEGATED) == 'true'
            Formula.attrib[XMLUtils.ATTRNEGATED] = 'false' if Flag else 'true'
            return Formula
        if Formula.tag == XMLUtils.NEGATION: # handle double negative
            Tmp = Formula[0]
            Formula.remove(Tmp)
            return Tmp
        if Formula.tag == XMLUtils.DISJUNCTION: # handle disjunctions (de Morgarn)
            for SubFormula in Formula:
                Formula.replace(SubFormula,SATUtils._Negate(SubFormula))
            Formula.tag = XMLUtils.CONJUNCTION
            return Formula
        if Formula.tag == XMLUtils.CONJUNCTION: # handle conjunctions (de Morgan)
            for SubFormula in Formula:
                Formula.replace(SubFormula,SATUtils._Negate(SubFormula))
            Formula.tag = XMLUtils.DISJUNCTION
            return Formula


    def _Flatten(Formula):
        for Elem in Formula:
            SATUtils._Flatten(Elem)
        if Formula.tag in [ XMLUtils.CONJUNCTION, XMLUtils.DISJUNCTION ]:
            Elems = list(Formula)
            Formula.clear()
            for Elem in Elems:
                if Elem.tag == Formula.tag:
                    Tmp = list(Elem)
                    Elem.clear()
                    Formula.extend(Tmp)
                else:
                    Formula.append(Elem)


    def _IsVariable(Formula):
        return Formula.tag == XMLUtils.VARIABLE


    def _IsConstant(Formula):
        return Formula.tag == XMLUtils.CONSTANT


    def _IsTrueConstant(Formula):
        return SATUtils._IsConstant(Formula) and Formula.attrib[XMLUtils.ATTRVALUE] == "true"


    def _IsFalseConstant(Formula):
        return SATUtils._IsConstant(Formula) and Formula.attrib[XMLUtils.ATTRVALUE] == "false"


    def _IsLiteral(Formula):
        return SATUtils._IsVariable(Formula) or SATUtils._IsConstant(Formula)


    def _IsNegatedLiteral(Formula):
        return SATUtils._IsNegation(Formula) and SATUtils._IsLiteral(Formula[0])


    def _IsNegation(Formula):
        return Formula.tag == XMLUtils.NEGATION


    def _IsConjunction(Formula):
        return Formula.tag == XMLUtils.CONJUNCTION


    def _IsDisjunction(Formula):
        return Formula.tag == XMLUtils.DISJUNCTION


    def _IsClause(Formula):
        if SATUtils._IsLiteral(Formula):
            return True
        elif Formula.tag == XMLUtils.DISJUNCTION:
            return all(map(SATUtils._IsLiteral,Formula))
        else:
            return False


    def _IsDisjConj(Formula):
        return SATUtils._IsDisjunction(Formula) and SATUtils._IsConjunction(Formula[1])


    def _IsConjDisj(Formula):
        return SATUtils._IsDisjunction(Formula) and SATUtils._IsConjunction(Formula[0])


    def _IsDoubleNegation(Formula):
        return SATUtils._IsNegation(Formula) and SATUtils._IsNegation(Formula[0])


    def _IsNegatedConjDisj(Formula):
        return SATUtils._IsNegation(Formula) and ( SATUtils._IsConjunction(Formula[0]) or SATUtils._IsDisjunction(Formula[0]) )


    def _IsNegatedDisjunction(Formula):
        return SATUtils._IsNegation(Formula) and SATUtils._IsDisjunction(Formula[0])


    def _Split(Elems,Tag):
        if len(Elems) == 1:
            return Elems[0]
        else:
            Middle = int(len(Elems)/2)
            Buf1 = Elems[:Middle]
            Buf2 = Elems[Middle:]

            Op = XMLUtils.conjunction() if Tag == XMLUtils.CONJUNCTION else XMLUtils.disjunction()
            Op.append(SATUtils._Split(Buf1,Tag))
            Op.append(SATUtils._Split(Buf2,Tag))
            return Op


    def _ConvertBinaryForm(Formula):
        if SATUtils._IsLiteral(Formula):
            return Formula

        elif SATUtils._IsConjunction(Formula) or SATUtils._IsDisjunction(Formula):
            Elems = list(Formula)
            Formula.clear()

            Formula.extend(map(SATUtils._ConvertBinaryForm,list(SATUtils._Split(Elems,Formula.tag))))

            return Formula

        elif SATUtils._IsNegation(Formula):
            Tmp = Formula[0]
            Formula.clear()
            return SATUtils._ConvertBinaryForm(Tmp)
        else:
            return SATUtils._ConvertBinaryForm(Formula[0])


    def _PushNegation(Formula):
        if SATUtils._IsDoubleNegation(Formula):
            Tmp = Formula[0][0]
            Formula.clear()
            return SATUtils._PushNegation(Tmp)

        elif SATUtils._IsNegatedLiteral(Formula):
            Tmp = Formula[0]
            Formula.clear()
            return SATUtils._Negate(Tmp)

        elif SATUtils._IsNegatedConjDisj(Formula):
            Tmp = Formula[0]
            Tag = Tmp.tag
            Formula.clear()
            Formula.extend([SATUtils._PushNegation(SATUtils._Negate(Elem)) for Elem in Tmp])
            Formula.tag = XMLUtils.DISJUNCTION if SATUtils._IsConjunction(Formula) else XMLUtils.CONJUNCTION
            return Formula

        elif SATUtils._IsConjunction(Formula) or SATUtils._IsDisjunction(Formula):
            Elems = list(Formula)
            Formula.clear()
            Formula.extend([SATUtils._PushNegation(Elem) for Elem in Elems])
            return Formula

        else:
            return Formula


    def _ConvertDNCToCNF(Formula):
        Tmp = SATUtils._PushNegation(Formula)
        Tmp2 = SATUtils._ConvertBinaryForm(Tmp)
        Formula = SATUtils._ConvertDNCToCNFRecurse(Tmp2)
        return Formula


    def _ConvertDNCToCNFRecurse(Formula):
        if SATUtils._IsConjunction(Formula):
            Elems = list(Formula)
            Formula.clear()
            for Elem in Elems:
                Formula.append(SATUtils._ConvertDNCToCNFRecurse(Elem))
            return Formula

        elif SATUtils._IsDisjunction(Formula):
            Elems = list(Formula)
            Formula.clear()
            for Elem in Elems:
                Formula.append(SATUtils._ConvertDNCToCNFRecurse(Elem))
            return SATUtils._Distribute(Formula)
        else:
            return Formula


    def _Distribute(Formula):
            return SATUtils._DistributeRight(SATUtils._DistributeLeft(Formula))


    def _DistributeRight(Formula):
        if SATUtils._IsDisjConj(Formula):
            FirstElem = Formula[0]
            SecondElem = Formula[1][0]
            ThirdElem = Formula[1][1:]
            Formula.clear()

            Formula.tag = XMLUtils.CONJUNCTION

            Dis1 = XMLUtils.disjunction()
            Dis1.append(FirstElem)
            Dis1.append(SecondElem)
            Formula.append(SATUtils._DistributeRight(Dis1))

            for Elem in list(ThirdElem):
                Dis2 = XMLUtils.disjunction()
                Dis2.append(deepcopy(FirstElem))
                Dis2.append(Elem)
                Formula.append(SATUtils._DistributeRight(Dis2))

            return Formula
        else:
            return Formula


    def _DistributeLeft(Formula):
        if SATUtils._IsConjDisj(Formula):
            FirstElem = Formula[0][0]
            SecondElem = Formula[0][1:]
            ThirdElem = Formula[1]
            Formula.clear()

            Formula.tag = XMLUtils.CONJUNCTION

            Dis1 = XMLUtils.disjunction()
            Dis1.append(FirstElem)
            Dis1.append(ThirdElem)
            Formula.append(SATUtils._DistributeLeft(Dis1))

            for Elem in list(SecondElem):
                Dis2 = XMLUtils.disjunction()
                Dis2.append(Elem)
                Dis2.append(deepcopy(ThirdElem))
                Formula.append(SATUtils._DistributeLeft(Dis2))

            return Formula
        else:
            return Formula


    def ConvertToCNF(Formula):
        SATUtils._ReduceToDNC(Formula)
        try:
            Tmp = Formula[0]
            Formula.remove(Tmp)
            Formula.append(SATUtils._ConvertDNCToCNF(Tmp))
        except Exception as er:
            exit(1)
        SATUtils._Flatten(Formula)

