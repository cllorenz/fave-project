# -*- coding: utf-8 -*-

# Copyright 2018 Vera Clemens

# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

import ast
import copy
from policy_exceptions import *

class Policy(object):
	"""Represents a security policy for a computer network. Contains roles,
	services and reachability policies.

	Attributes:
		roles: A dictionary of Role and Superrole objects that group together
			a number of hosts. Contains at least the role named "Internet".
		services: A dictionary of Service objects that represent a service
			accessible using a certain port and protocol.
		policies: A dictionary of ReachabilityPolicy objects that specify
			whether one role should be able to reach another and under what
			conditions.
		default_policy: A boolean value indicating whether the default policy
			is "deny" (False) or "allow" (True).
	"""

	def __init__(self):
		"""Initialises a Policy object with role "Internet", no services, no
		policies and default policy "deny"."""

		self.roles = {}
		self.services = {}
		self.policies = {}
		self.default_policy = False
		self.add_role("Internet")

	def add_role(self, name):
		"""Adds a role.

		Args:
			name: A string.

		Raises:
			NameTakenException: A role or service with this name already exists.
		"""

		if (self.role_exists(name)) or (self.service_exists(name)):
			raise NameTakenException(name)

		self.roles[name] = Role(name, self)

	def add_superrole(self, name):
		"""Adds a superrole.

		Args:
			name: A string.

		Raises:
			NameTakenException: A role or service with this name already exists.
		"""

		if (self.role_exists(name)) or (self.service_exists(name)):
			raise NameTakenException(name)

		self.roles[name] = Superrole(name, self)

	def add_service(self, name):
		"""Adds a service.

		Args:
			name: A string.

		Raises:
			NameTakenException: A role or service with this name already exists.
		"""

		if (self.role_exists(name)) or (self.service_exists(name)):
			raise NameTakenException(name)

		self.services[name] = Service(name, self)

	def role_exists(self, name):
		"""Returns whether a role with the given name exists or not.

		Args:
			name: A string.

		Returns:
			A boolean.
		"""

		return name in self.roles.keys()

	def service_exists(self, name):
		"""Returns whether a service with the given name exists or not.

		Args:
			name: A string.

		Returns:
			A boolean.
		"""

		return name in self.services.keys()

	def policy_exists(self, role_from, role_to):
		"""Returns whether a reachability policy concerning the two given roles
		exists or not.

		Args:
			role_from: A string.
			role_to: A string.

		Returns:
			A boolean.
		"""

		return (role_from, role_to) in self.policies.keys()

	def add_reachability_policy(self, role_from, role_to, service_to=None, condition=None):
		"""Adds or updates a reachability policy concerning two roles.

		If one or both of the roles are superroles, reachability policies will
		be added or updated for all combinations of their subroles.

		If a service is specified, its attributes will be added as conditions.
		If the service specified is "*" (wildcard), all services of the reached
		role will be considered. If the reached role is a superrole, all
		subservices will be considered. They are added as conditions separately
		(multiple "OR" operands).

		Args:
			role_from: A string.
			role_to: A string.
			service_to: A string.
			condition: A dictionary.

		Raises:
			RoleUnknownException: At least one of the roles is not known.
			ServiceUnknownException: Service is not known to at least one role.
		"""

		if not self.role_exists(role_from):
			raise RoleUnknownException(role_from)
		if not self.role_exists(role_to):
			raise RoleUnknownException(role_to)

		roles_from, roles_to = self.roles[role_from].get_roles(), self.roles[role_to].get_roles()

		for role_from in roles_from:
			for role_to in roles_to:
				conditions = [copy.deepcopy(condition)] if condition is not None else []

				if service_to == "*":
					services = self.roles[role_to].get_services()
					services = services[role_to]
				else:
					services = [service_to] if service_to is not None else []

				for service in services:
					if self.roles[role_to].offers_service(service):
						conditions.append(copy.deepcopy(self.services[service].attributes))
					else:
						raise ServiceUnknownException(service, role_to)

				if not self.policy_exists(role_from, role_to):
					self.policies[(role_from, role_to)] = ReachabilityPolicy(role_from, role_to, self, conditions)
				else:
					self.policies[(role_from, role_to)].update_conditions(conditions)

	def set_default_policy(self, default):
		"""Sets the default policy.

		Args:
			default: Either "deny" or "allow".
		"""

		if default == "deny":
			self.default_policy = False
		elif default == "allow":
			self.default_policy = True

	def to_html(self):
		"""Creates a reachability table in HTML format using roles (not
		superroles) as table headings.

		Role attributes as well as reachability conditions are presented in
		boxes that are visible when performing a mouseover over the table cells.

		Returns:
			A string that is an HTML file containing a reachability table.
		"""

		roles = {name: role for name, role in self.roles.iteritems() if type(role) == Role}

		html_list = ["<!DOCTYPE html>\n",
		"<html>\n",
		"\t<head>\n",
		"\t\t<meta charset='UTF-8'>\n",
		"\t\t<title>Policy-Translator -- HTML-Ausgabe</title>\n",
		"\t\t<link rel='stylesheet' href='policies.css'>\n",
		"\t</head>\n",
		"\t<body>\n",
		"\t\t<table>\n",
		"\t\t\t<tr>\n",
		"\t\t\t\t<td></td>\n",
		"\t\t\t\t<td></td>\n",
		"\t\t\t\t<td class='label' colspan='%d'>ZIEL</td>\n" % len(roles),
		"\t\t\t</tr>\n",
		"\t\t\t<tr>\n",
		"\t\t\t\t<td></td>\n",
		"\t\t\t\t<td></td>\n"]

		for role in roles:
			html_list.append(("\t\t\t\t<td class='role'>\n"
			"\t\t\t\t\t<div class='tooltip'>\n"
			"\t\t\t\t\t\t" + role + "\n"
			"\t\t\t\t\t\t<span class='tooltiptext'>"))
			for key, value in self.roles[role].attributes.iteritems():
				html_list.append("%s = %s<br/>" % (key, value))
	 		html_list.append(("</span>\n"
			"\t\t\t\t\t</div>\n"
			"\t\t\t\t</td>\n"))

		html_list.append("\t\t\t</tr>\n")

		for counter, role_from in enumerate(roles):
			html_list.append("\t\t\t<tr>\n")

			if counter == 0:
				html_list.append("\t\t\t\t<td class='label' rowspan='%d'>Q<br/>U<br/>E<br/>L<br/>L<br/>E</td>\n" % len(roles))

			html_list.append("\t\t\t\t<td class='role'>%s</td>\n" % role_from)

			for role_to in roles:
				if role_from == "Internet" and role_to == "Internet":
					html_list.append("\t\t\t\t<td>&nbsp;</td>\n")
				elif (role_from, role_to) in self.policies and len(self.policies[(role_from, role_to)].conditions) > 0:
						html_list.append(("\t\t\t\t<td class='cond_allowed'>\n"
						"\t\t\t\t\t<div class='tooltip'>\n"
						"\t\t\t\t\t\t&#x2705;\n"
						"\t\t\t\t\t\t<span class='tooltiptext'>"))
						if self.default_policy:
							html_list.append("NICHT<br/>(</br>")
						for counter, cond in enumerate(self.policies[(role_from, role_to)].conditions):
							if not counter == 0:
								html_list.append("ODER<br/>")
							for key, value in cond.iteritems():
								html_list.append("%s = %s<br/>" % (key, value))
						if self.default_policy:
							html_list.append(")")
				 		html_list.append(("</span>\n"
						"\t\t\t\t\t</div>\n"
						"\t\t\t\t</td>\n"))
				elif (self.default_policy ^ ((role_from, role_to) in self.policies)):
					html_list.append("\t\t\t\t<td class='allowed'>&#x2705;</td>\n")
				else:
					html_list.append("\t\t\t\t<td class='disallowed'>&#x274c;</td>\n")

			html_list.append("\t\t\t</tr>\n")

		html_list.append(("\t\t</table>\n\n"
		"\t\t<br/><br/>\n"
		"\t\t<h3>Legende:</h3>\n\n"
		"\t\t<table>\n"
		"\t\t\t<tr>\n"
		"\t\t\t\t<td class='allowed'>&#x2705;</td>\n"
		"\t\t\t\t<td>Erlaubt</td>\n"
		"\t\t\t</tr>\n"
		"\t\t\t<tr>\n"
		"\t\t\t\t<td class='cond_allowed'>&#x2705;</td>\n"
		"\t\t\t\t<td>Nur bedingt erlaubt (Mouseover für mehr Informationen)</td>\n"
		"\t\t\t</tr>\n"
		"\t\t\t<tr>\n"
		"\t\t\t\t<td class='disallowed'>&#x274c;</td>\n"
		"\t\t\t\t<td>Nicht erlaubt</td>\n"
		"\t\t\t</tr>\n"
		"\t\t</table>\n"
		"\t</body>\n"
		"</html>"))

		return "".join(html_list)

	def vlans_to_csv(self):
		"""Creates a reachability table in CSV format using VLANs as table
		headings.

		Returns:
			A string that is a CSV file containing a reachability table.
		"""

		roles = {name: role for name, role in self.roles.iteritems() if type(role) == Role}
		vlans, csv_list = set(), []

		for name, role in roles.iteritems():
			if "vlan" in role.attributes:
				vlans.add(role.attributes["vlan"])

		reachable = {(id, id) for id in vlans}

		for policy in self.policies:
			if ("vlan" in self.roles[policy[0]].attributes) and ("vlan" in self.roles[policy[1]].attributes):
				vlan_from = self.roles[policy[0]].attributes["vlan"]
				vlan_to = self.roles[policy[1]].attributes["vlan"]
				reachable.add((vlan_from, vlan_to))

		for vlan in vlans:
			csv_list.append(",%d" % vlan)

		csv_list.append("\n")

		for vlan_from in vlans:
			csv_list.append("%d" % vlan_from)
			for vlan_to in vlans:
				if (vlan_from, vlan_to) in reachable:
					csv_list.append(",X")
				else:
					csv_list.append(",")
			csv_list.append("\n")

		return "".join(csv_list)

class Role(object):
	"""Represents a set of hosts that have certain attributes and offer certain
	services.

	Attributes:
		name: A string.
		policy: A Policy object that the role belongs to.
		attributes: A dictionary containing attributes and their values.
		services: A dictionary containing service names as keys and Service
			objects as values.
	"""

	valid_role_attr = ["hosts", "vlan"]

	def __init__(self, name, policy, attributes=None, services=None):
		"""Initialises a Role object with the given name, policy, attributes and
		services.

		Args:
			name: A string.
			policy: A Policy object.
			attributes: A dictionary. (default: {})
			services: A dictionary. (default: {})
		"""

		self.name = name
		self.policy = policy
		self.attributes = attributes if attributes is not None else {}
		self.services = services if services is not None else {}

	def add_attribute(self, key, value):
		"""Sets an attribute value. If already set, it will be overwritten.

		Args:
			key: A string.
			value: A string; may be a list in string from. (example:
				"['a', 'b']")

		Raises:
			InvalidValueException: Value could not be read.
			InvalidAttributeException: Attribute is not part of the list of
				valid attributes.
		"""

		if key in self.valid_role_attr:
			try:
				self.attributes[key] = ast.literal_eval(value)
			except Exception:
				raise InvalidValueException(key, value)
		else:
			raise InvalidAttributeException(key)

	def add_service(self, name):
		"""Adds an existing service to the role.

		Args:
			name: A string.

		Raises:
			ServiceUnknownException: Service name is not known to the Policy
				object.
		"""

		if self.policy.service_exists(name):
			self.services[name] = self.policy.services[name]
		else:
			raise ServiceUnknownException(name)

	def get_roles(self):
		"""Returns a list of all roles that are represented by this role, i.e.,
		a list containing only itself.

		Returns:
			A list containing the role name.
		"""

		return [self.name]

	def get_services(self):
		"""Returns a dictionary of all roles that are represented by this role
		as keys, i.e., only itself, and a dictionary of all services of those
		roles, i.e., its services.

		Returns:
			A dictionary containing the role name as key and the services
			dictionary as value.
		"""

		return {self.name: self.services}

	def offers_services(self):
		"""Checks whether this role offers services or not.

		Returns:
			A boolean value.
		"""

		return len(self.services) > 0

	def offers_service(self, name):
		"""Checks whether this role offers a certain service or not.

		Returns:
			A boolean value.
		"""

		return name in self.services

class Superrole(Role):
	"""Contains a set of roles. May contain all services of a role or only a
	certain subset of services.

	Attributes:
		name: A string.
		policy: A Policy object that the superrole belongs to.
		subroles: A dictionary containing role names as keys and Role
			objects as values.
		subservices: A dictionary containing role names as keys and dictionaries
		 	containing service names as keys and Service objects as values.
	"""

	def __init__(self, name, policy, subroles=None, subservices=None):
		"""Initialises a Superrole object with the given name, policy, subroles
		and subservices.

		Args:
			name: A string.
			policy: A Policy object.
			subroles: A dictionary. (default: {})
			subservices: A dictionary. (default: {})
		"""

		self.name = name
		self.policy = policy
		self.subroles = subroles if subroles is not None else {}
		self.subservices = subservices if subservices is not None else {}

	def add_attribute(self, key, value):
		"""Sets an attribute value for all subroles. See base class."""

		for subrole in self.subroles.values():
			subrole.add_attribute(key, value)

	def add_subrole(self, name, service):
		"""Adds a subrole along with a service as subservice (optional).

		If the subrole added is a superrole, all of its subroles will be added
		in its stead. If a service name is given, only that service will be
		added as subservice. If no service name is given, only those services
		of the role that are subservices in the superrole will be added as
		subservices here (may be None).

		Args:
			name: A string.
			service: A string.

		Raises:
			RoleUnknownException: Role name is not known to the Policy object.
		"""

		if self.policy.role_exists(name):
			new_subrole = self.policy.roles[name]

			if type(new_subrole) == Superrole:
				for subrole in new_subrole.get_roles():
					if service is None:
						self.subroles[subrole] = self.policy.roles[subrole]
						self.subservices[subrole] = new_subrole.subservices[subrole]
					else:
						self.add_subrole(subrole, service)
			else:
				self.subroles[name] = new_subrole
				if name not in self.subservices.keys():
					self.subservices[name] = {}
				if service is not None:
					self.add_subservice(name, service)
		else:
			raise RoleUnknownException(name)

	def add_subservice(self, subrole, service):
		"""Adds one or all services of a subrole as subservices.

		Args:
			subrole: A string.
			service: A string, may be "*" (wildcard).

		Raises:
			ServiceUnknownException: Service name is not known to the Role
				object.
		"""

		if (service == "*"):
			for service in self.policy.roles[subrole].services:
				self.subservices[subrole][service] = self.policy.services[service]
		elif self.policy.roles[subrole].offers_service(service):
			self.subservices[subrole][service] = self.policy.services[service]
		else:
			raise ServiceUnknownException(service, subrole)

	def add_service(self, service):
		"""Adds a service to all subroles and adds that service as subservice
		for all roles.

		Args:
			service: A string.
		"""

		for subrole in self.subroles.values():
			subrole.add_service(service)
		for subrole in self.subroles.keys():
			self.add_subservice(subrole, service)

	def get_roles(self):
		"""Returns a list of all roles that are represented by this role, i.e.,
		a list containing all subroles.

		Returns:
			A list containing the role names of all subroles.
		"""

		return self.subroles.keys()

	def get_services(self):
		"""Returns a dictionary of all roles that are represented by this role
		as keys, i.e., all subroles, and a dictionary of subservices of those
		roles.

		Returns:
			A dictionary containing the subrole names as keys and the
			subservices dictionaries as values.
		"""

		return self.subservices

	def offers_services(self):
		"""Checks whether this role offers services or not.

		Returns:
			False. (Only roles offer services.)
		"""

		return False

	def offers_service(self, name):
		"""Checks whether this role offers a certain service or not.

		Returns:
			False. (Only roles offer services.)
		"""

		return False

class Service(object):
	"""Represents a service, i.e., a certain port and/or transport layer
	protocol.

	Attributes:
		name: A string.
		policy: A Policy object that the role belongs to.
		attributes: A dictionary containing attributes and their values.
	"""

	valid_role_attr = ["protocol", "port"]

	def __init__(self, name, policy, attributes=None):
		"""Initialises a Service object with the given name, policy, attributes
		and	services.

		Args:
			name: A string.
			policy: A Policy object.
			attributes: A dictionary. (default: {})
		"""

		self.name = name
		self.policy = policy
		self.attributes = attributes if attributes is not None else {}

	def add_attribute(self, key, value):
		"""Sets an attribute value. If already set, it will be overwritten.

		Args:
			key: A string.
			value: A string; may be a list in string from. (example:
				"['a', 'b']")

		Raises:
			InvalidValueException: Value could not be read.
			InvalidAttributeException: Attribute is not part of the list of
				valid attributes.
		"""

		if key in self.valid_role_attr:
			try:
				self.attributes[key] = ast.literal_eval(value)
			except Exception:
				raise InvalidValueException(key, value)
		else:
			raise InvalidAttributeException(key)

class ReachabilityPolicy(object):
	"""Represents a reachability policy from one role to another that differs
	from the default policy.

	Attributes:
		role_from: A string.
		role_to: A string.
		policy: A Policy object.
		conditions: A list of dictionaries containing attribute-value-pairs
			that specify some condition, e.g., "port": 22.
			All list entries are considered to be connected by "OR".
			Semantics differ depending on the default policy of the Policy
			object this reachability policy belongs to. If the default policy
			is "deny", these are the conditions under which reachability will
			be allowed. If the default policy is "allow", these are the
			conditions under which reachability will be denied.
	"""

	def __init__(self, role_from, role_to, policy, conditions=None):
		"""Initialises a ReachabilityPolicy object with the given role names,
		policy and conditions.

		Args:
			name: A string.
			policy: A Policy object.
			conditions: A list of dictionaries. (default: [])
		"""

		self.role_from = role_from
		self.role_to = role_to
		self.policy = policy
		self.conditions = copy.deepcopy(conditions) if conditions is not None else []

	def update_conditions(self, new_conditions):
		"""Adds or removes conditions.

		Each new condition is considered separately.
		If it is a superset of some condition that already exists (= more strict),
		it will be discarded.
		If it is a subset of some condition that already exists (= less strict),
		the already existing condition will be replaced by it.
		If it is neither, it will be added as an additional "OR" operand.

		An empty list of conditions means that reachability is allowed or denied
		(depending on the default policy) unconditionally. Therefore, the empty
		list overpowers all other lists of conditions.

		Args:
			new_conditions: A list of dictionaries.
		"""
		if self.conditions == []:
			return
		elif new_conditions == []:
			self.conditions = []
			return

		for new_condition in new_conditions:
			append = True
			for condition in self.conditions:
				if condition.viewitems() <= new_condition.viewitems():
					append = False
					break
				elif new_condition.viewitems() < condition.viewitems():
					self.conditions.remove(condition)
					break
			if append:
				self.conditions.append(new_condition)
