# README

## How to run

The Policy Translator was developed and tested with Python version 2.7.

It can be executed using the command

``./policy_translator.py COMBO-FILE``

(the specified file must contain an inventory first, followed by policies)

or

``./policy_translator.py INVENTORY-FILE POLICY-FILE``

(if inventory and policies are in separate files).

Export of reachability tables in HTML or CSV format can be toggled using the command-line options ``--html`` and ``--csv``.

## Example files

Two example files that contain both an inventory and policies are enclosed with the policy translator. 

1. ``examples/ifi-policy.txt``
2. ``examples/fml-paper-policy.txt``

They can be used as input files for the Policy Translator using the first command specified in the section above.

Example: ``./policy_translator.py --html --csv examples/ifi-policy.txt``

## License

Policy Translator is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

Policy Translator is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.
