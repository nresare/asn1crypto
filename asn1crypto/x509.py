# coding: utf-8

"""
ASN.1 type classes for X509 certificates. Exports the following items:

 - Attributes()
 - Certificate()
 - Extensions()
 - GeneralName()
 - GeneralNames()
 - Name()

Other type classes are defined that help compose the types listed above.
"""

from __future__ import unicode_literals, division, absolute_import, print_function

import sys
import re
import hashlib
import socket
from collections import OrderedDict

from .core import (
    Any,
    BitString,
    BMPString,
    Boolean,
    Choice,
    GeneralizedTime,
    GeneralString,
    IA5String,
    Integer,
    Null,
    NumericString,
    ObjectIdentifier,
    OctetBitString,
    OctetString,
    PrintableString,
    Sequence,
    SequenceOf,
    Set,
    SetOf,
    TeletexString,
    UniversalString,
    UTCTime,
    UTF8String,
    VisibleString,
)
from .algos import SignedDigestAlgorithm
from .keys import PublicKeyInfo
from ._int import int_to_bytes, int_from_bytes

if sys.version_info < (3,):
    str_cls = unicode  #pylint: disable=E0602
else:
    str_cls = str

if sys.platform == 'win32':
    from ._win._ws2_32 import inet_ntop, inet_pton
else:
    from socket import inet_ntop, inet_pton



# The structures in this file are taken from https://tools.ietf.org/html/rfc5280
# and a few other supplementary sources, mostly due to extra supported
# extension and name OIDs

class Attribute(Sequence):
    _fields = [
        ('type', ObjectIdentifier),
        ('values', SetOf, {'spec': Any}),
    ]


class Attributes(SequenceOf):
    _child_spec = Attribute


class KeyUsage(BitString):
    _map = {
        0: 'digital_signature',
        1: 'non_repudiation',
        2: 'key_encipherment',
        3: 'data_encipherment',
        4: 'key_agreement',
        5: 'key_cert_sign',
        6: 'crl_sign',
        7: 'encipher_only',
        8: 'decipher_only',
    }


class PrivateKeyUsagePeriod(Sequence):
    _fields = [
        ('not_before', GeneralizedTime, {'tag_type': 'implicit', 'tag': 0, 'optional': True}),
        ('not_after', GeneralizedTime, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
    ]


class DirectoryString(Choice):
    _alternatives = [
        ('teletex_string', TeletexString),
        ('printable_string', PrintableString),
        ('universal_string', UniversalString),
        ('utf8_string', UTF8String),
        ('bmp_string', BMPString),
    ]


class NameType(ObjectIdentifier):
    _map = {
        '2.5.4.3': 'common_name',
        '2.5.4.4': 'surname',
        '2.5.4.5': 'serial_number',
        '2.5.4.6': 'country_name',
        '2.5.4.7': 'locality_name',
        '2.5.4.8': 'state_or_province_name',
        '2.5.4.10': 'organization_name',
        '2.5.4.11': 'organizational_unit_name',
        '2.5.4.12': 'title',
        '2.5.4.15': 'business_category',
        '2.5.4.41': 'name',
        '2.5.4.42': 'given_name',
        '2.5.4.43': 'initials',
        '2.5.4.44': 'generation_qualifier',
        '2.5.4.46': 'dn_qualifier',
        # https://tools.ietf.org/html/rfc2985#page-26
        '1.2.840.113549.1.9.1': 'email_address',
        # Page 10 of https://cabforum.org/wp-content/uploads/EV-V1_5_5.pdf
        '1.3.6.1.4.1.311.60.2.1.1': 'incorporation_locality',
        '1.3.6.1.4.1.311.60.2.1.2': 'incorporation_state_or_province',
        '1.3.6.1.4.1.311.60.2.1.3': 'incorporation_country',
    }

    @property
    def human_friendly(self):
        """
        :return:
            A human-friendly unicode string to display to users
        """

        return {
            'common_name': 'Common Name',
            'surname': 'Surname',
            'serial_number': 'Serial Number',
            'country_name': 'Country',
            'locality_name': 'Locality',
            'state_or_province_name': 'State/Province',
            'organization_name': 'Organization',
            'organizational_unit_name': 'Organizational Unit',
            'title': 'Title',
            'business_category': 'Business Category',
            'name': 'Name',
            'given_name': 'Given Name',
            'initials': 'Initials',
            'generation_qualifier': 'Generation Qualifier',
            'dn_qualifier': 'DN Qualifier',
            'email_address': 'Email Address',
            'incorporation_locality': 'Incorporation Locality',
            'incorporation_state_or_province': 'Incorporation State/Province',
            'incorporation_country': 'Incorporation Country',
        }[self.native]


class NameTypeAndValue(Sequence):
    _fields = [
        ('type', NameType),
        ('value', Any),
    ]

    _oid_pair = ('type', 'value')
    _oid_specs = {
        'common_name': DirectoryString,
        'surname': DirectoryString,
        'serial_number': DirectoryString,
        'country_name': DirectoryString,
        'locality_name': DirectoryString,
        'state_or_province_name': DirectoryString,
        'organization_name': DirectoryString,
        'organizational_unit_name': DirectoryString,
        'title': DirectoryString,
        'name': DirectoryString,
        'given_name': DirectoryString,
        'initials': DirectoryString,
        'generation_qualifier': DirectoryString,
        'dn_qualifier': DirectoryString,
        # https://tools.ietf.org/html/rfc2985#page-26
        'email_address': IA5String,
        # Page 10 of https://cabforum.org/wp-content/uploads/EV-V1_5_5.pdf
        'incorporation_locality': DirectoryString,
        'incorporation_state_or_province': DirectoryString,
        'incorporation_country': DirectoryString,
    }


class RelativeDistinguishedName(SetOf):
    _child_spec = NameTypeAndValue


class RDNSequence(SequenceOf):
    _child_spec = RelativeDistinguishedName


class Name(Choice):
    _alternatives = [
        ('', RDNSequence),
    ]

    _human_friendly = None
    _sha1 = None
    _sha256 = None

    @property
    def native(self):
        if self.contents is None:
            return None
        if self._native is None:
            self._native = OrderedDict()
            for rdn in self.chosen.native:
                for type_val in rdn:
                    field_name = type_val['type']
                    if field_name in self._native:
                        self._native[field_name] = [self._native[field_name]]
                        self._native[field_name].append(type_val['value'])
                    else:
                        self._native[field_name] = type_val['value']
        return self._native

    @property
    def human_friendly(self):
        """
        :return:
            A human-friendly unicode string containing the parts of the name
        """

        if self._human_friendly is None:
            data = OrderedDict()
            for rdn in self.chosen:
                for type_val in rdn:
                    field_name = type_val['type'].human_friendly
                    if field_name in data:
                        data[field_name] = [data[field_name]]
                        data[field_name].append(type_val['value'])
                    else:
                        data[field_name] = type_val['value']
            to_join = []
            for key in data:
                value = data[key]
                if isinstance(value, list):
                    value = ', '.join(value)
                to_join.append('%s: %s' % (key, value.native))

            has_comma = False
            for element in to_join:
                if element.find(',') != -1:
                    has_comma = True
                    break

            separator = ', ' if not has_comma else '; '
            self._human_friendly = separator.join(to_join[::-1])

        return self._human_friendly

    @property
    def sha1(self):
        """
        :return:
            The SHA1 hash of the DER-encoded bytes of this name
        """

        if self._sha1 is None:
            self._sha1 = hashlib.sha1(self.dump()).digest()
        return self._sha1

    @property
    def sha256(self):
        """
        :return:
            The SHA-256 hash of the DER-encoded bytes of this name
        """

        if self._sha256 is None:
            self._sha256 = hashlib.sha256(self.dump()).digest()
        return self._sha256


class AnotherName(Sequence):
    _fields = [
        ('type_id', ObjectIdentifier),
        ('value', Any, {'tag_type': 'explicit', 'tag': 0}),
    ]


class CountryName(Choice):
    class_ = 1
    tag = 1

    _alternatives = [
        ('x121_dcc_code', NumericString),
        ('iso_3166_alpha2_code', PrintableString),
    ]


class AdministrationDomainName(Choice):
    class_ = 1
    tag = 2

    _alternatives = [
        ('numeric', NumericString),
        ('printable', PrintableString),
    ]


class PrivateDomainName(Choice):
    _alternatives = [
        ('numeric', NumericString),
        ('printable', PrintableString),
    ]


class PersonalName(Set):
    _fields = [
        ('surname', PrintableString, {'tag_type': 'implicit', 'tag': 0}),
        ('given_name', PrintableString, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
        ('initials', PrintableString, {'tag_type': 'implicit', 'tag': 2, 'optional': True}),
        ('generation_qualifier', PrintableString, {'tag_type': 'implicit', 'tag': 3, 'optional': True}),
    ]


class TeletexPersonalName(Set):
    _fields = [
        ('surname', TeletexString, {'tag_type': 'implicit', 'tag': 0}),
        ('given_name', TeletexString, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
        ('initials', TeletexString, {'tag_type': 'implicit', 'tag': 2, 'optional': True}),
        ('generation_qualifier', TeletexString, {'tag_type': 'implicit', 'tag': 3, 'optional': True}),
    ]


class OrganizationalUnitNames(SequenceOf):
    _child_spec = PrintableString


class TeletexOrganizationalUnitNames(SequenceOf):
    _child_spec = TeletexString


class BuiltInStandardAttributes(Sequence):
    _fields = [
        ('country_name', CountryName, {'optional': True}),
        ('administration_domain_name', AdministrationDomainName, {'optional': True}),
        ('network_address', NumericString, {'tag_type': 'implicit', 'tag': 0, 'optional': True}),
        ('terminal_identifier', PrintableString, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
        ('private_domain_name', PrivateDomainName, {'tag_type': 'explicit', 'tag': 2, 'optional': True}),
        ('organization_name', PrintableString, {'tag_type': 'implicit', 'tag': 3, 'optional': True}),
        ('numeric_user_identifier', NumericString, {'tag_type': 'implicit', 'tag': 4, 'optional': True}),
        ('personal_name', PersonalName, {'tag_type': 'implicit', 'tag': 5, 'optional': True}),
        ('organizational_unit_names', OrganizationalUnitNames, {'tag_type': 'implicit', 'tag': 6, 'optional': True}),
    ]


class BuiltInDomainDefinedAttribute(Sequence):
    _fields = [
        ('type', PrintableString),
        ('value', PrintableString),
    ]


class BuiltInDomainDefinedAttributes(SequenceOf):
    _child_spec = BuiltInDomainDefinedAttribute


class TeletexDomainDefinedAttribute(Sequence):
    _fields = [
        ('type', TeletexString),
        ('value', TeletexString),
    ]


class TeletexDomainDefinedAttributes(SequenceOf):
    _child_spec = TeletexDomainDefinedAttribute


class PhysicalDeliveryCountryName(Choice):
    _alternatives = [
        ('x121_dcc_code', NumericString),
        ('iso_3166_alpha2_code', PrintableString),
    ]


class PostalCode(Choice):
    _alternatives = [
        ('numeric_code', NumericString),
        ('printable_code', PrintableString),
    ]


class PDSParameter(Set):
    _fields = [
        ('printable_string', PrintableString, {'optional': True}),
        ('teletex_string', TeletexString, {'optional': True}),
    ]


class PrintableAddress(SequenceOf):
    _child_spec = PrintableString


class UnformattedPostalAddress(Set):
    _fields = [
        ('printable_address', PrintableAddress, {'optional': True}),
        ('teletex_string', TeletexString, {'optional': True}),
    ]


class E1634Address(Sequence):
    _fields = [
        ('number', NumericString, {'tag_type': 'implicit', 'tag': 0}),
        ('sub_address', NumericString, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
    ]


class NAddresses(SetOf):
    _child_spec = OctetString


class PresentationAddress(Sequence):
    _fields = [
        ('p_selector', OctetString, {'tag_type': 'explicit', 'tag': 0, 'optional': True}),
        ('s_selector', OctetString, {'tag_type': 'explicit', 'tag': 1, 'optional': True}),
        ('t_selector', OctetString, {'tag_type': 'explicit', 'tag': 2, 'optional': True}),
        ('n_addresses', NAddresses, {'tag_type': 'explicit', 'tag': 3}),
    ]


class ExtendedNetworkAddress(Choice):
    _alternatives = [
        ('e163_4_address', E1634Address),
        ('psap_address', PresentationAddress, {'tag_type': 'implicit', 'tag': 0})
    ]


class TerminalType(Integer):
    _map = {
        3: 'telex',
        4: 'teletex',
        5: 'g3_facsimile',
        6: 'g4_facsimile',
        7: 'ia5_terminal',
        8: 'videotex',
    }


class ExtensionAttributeType(Integer):
    _map = {
        1: 'common_name',
        2: 'teletex_common_name',
        3: 'teletex_organization_name',
        4: 'teletex_personal_name',
        5: 'teletex_organization_unit_names',
        6: 'teletex_domain_defined_attributes',
        7: 'pds_name',
        8: 'physical_delivery_country_name',
        9: 'postal_code',
        10: 'physical_delivery_office_name',
        11: 'physical_delivery_office_number',
        12: 'extension_of_address_components',
        13: 'physical_delivery_personal_name',
        14: 'physical_delivery_organization_name',
        15: 'extension_physical_delivery_address_components',
        16: 'unformatted_postal_address',
        17: 'street_address',
        18: 'post_office_box_address',
        19: 'poste_restante_address',
        20: 'unique_postal_name',
        21: 'local_postal_attributes',
        22: 'extended_network_address',
        23: 'terminal_type',
    }


class ExtensionAttribute(Sequence):
    _fields = [
        ('extension_attribute_type', ExtensionAttributeType, {'tag_type': 'implicit', 'tag': 0}),
        ('extension_attribute_value', Any, {'tag_type': 'explicit', 'tag': 1}),
    ]

    _oid_pair = ('extension_attribute_type', 'extension_attribute_value')
    _oid_specs = {
        'common_name': PrintableString,
        'teletex_common_name': TeletexString,
        'teletex_organization_name': TeletexString,
        'teletex_personal_name': TeletexPersonalName,
        'teletex_organization_unit_names': TeletexOrganizationalUnitNames,
        'teletex_domain_defined_attributes': TeletexDomainDefinedAttributes,
        'pds_name': PrintableString,
        'physical_delivery_country_name': PhysicalDeliveryCountryName,
        'postal_code': PostalCode,
        'physical_delivery_office_name': PDSParameter,
        'physical_delivery_office_number': PDSParameter,
        'extension_of_address_components': PDSParameter,
        'physical_delivery_personal_name': PDSParameter,
        'physical_delivery_organization_name': PDSParameter,
        'extension_physical_delivery_address_components': PDSParameter,
        'unformatted_postal_address': UnformattedPostalAddress,
        'street_address': PDSParameter,
        'post_office_box_address': PDSParameter,
        'poste_restante_address': PDSParameter,
        'unique_postal_name': PDSParameter,
        'local_postal_attributes': PDSParameter,
        'extended_network_address': ExtendedNetworkAddress,
        'terminal_type': TerminalType,
    }


class ExtensionAttributes(SequenceOf):
    _child_spec = ExtensionAttribute


class ORAddress(Sequence):
    _fields = [
        ('built_in_standard_attributes', BuiltInStandardAttributes),
        ('built_in_domain_defined_attributes', BuiltInDomainDefinedAttributes, {'optional': True}),
        ('extension_attributes', ExtensionAttributes, {'optional': True}),
    ]


class EDIPartyName(Sequence):
    _fields = [
        ('name_assigner', DirectoryString, {'tag_type': 'implicit', 'tag': 0, 'optional': True}),
        ('party_name', DirectoryString, {'tag_type': 'implicit', 'tag': 1}),
    ]


class IPAddress(OctetString):
    def parse(self, spec=None, spec_params=None):
        """
        This method is not applicable to IP addresses
        """

        raise ValueError('IP address values can not be parsed')

    def set(self, value):
        """
        Sets the value of the object

        :param value:
            A unicode string containing an IPv4 address, IPv4 address with CIDR,
            an IPv6 address or IPv6 address with CIDR
        """

        if not isinstance(value, str_cls):
            raise ValueError('%s value must be a unicode string, not %s' % (self.__class__.__name__, value.__class__.__name__))

        original_value = value

        has_cidr = value.find('/') != -1
        cidr = 0
        if has_cidr:
            parts = value.split('/', 1)
            value = parts[0]
            cidr = int(parts[1])
            if cidr < 0:
                raise ValueError('%s value contains a CIDR range less than 0' % self.__class__.__name__)

        if value.find(':') != -1:
            family = socket.AF_INET6
            if cidr > 128:
                raise ValueError('%s value contains a CIDR range bigger than 128, the maximum value for an IPv6 address' % self.__class__.__name__)
            cidr_size = 128
        else:
            family = socket.AF_INET
            if cidr > 32:
                raise ValueError('%s value contains a CIDR range bigger than 32, the maximum value for an IPv4 address' % self.__class__.__name__)
            cidr_size = 32

        cidr_bytes = b''
        if has_cidr:
            cidr_mask = '1' * cidr
            cidr_mask += '0' * (cidr_size - len(cidr_mask))
            cidr_bytes = int_to_bytes(int(cidr_mask, 2))
            cidr_bytes = (b'\x00' * ((cidr_size // 8) - len(cidr_bytes))) + cidr_bytes

        self._native = original_value
        self.contents = inet_pton(family, value) + cidr_bytes
        self.header = None
        if self.trailer != b'':
            self.trailer = b''

    @property
    def native(self):
        """
        The a native Python datatype representation of this value

        :return:
            A unicode string or None
        """

        if self.contents is None:
            return None

        if self._native is None:
            byte_string = self.__bytes__()
            byte_len = len(byte_string)
            cidr_int = None
            if byte_len in {32, 16}:
                value = inet_ntop(socket.AF_INET6, byte_string[0:16])
                if byte_len > 16:
                    cidr_int = int_from_bytes(byte_string[16:])
            elif byte_len in {8, 4}:
                value = inet_ntop(socket.AF_INET, byte_string[0:4])
                if byte_len > 4:
                    cidr_int = int_from_bytes(byte_string[4:])
            if cidr_int is not None:
                cidr_bits = '{0:b}'.format(cidr_int)
                cidr = len(cidr_bits.rstrip('0'))
                value = value + '/' + str_cls(cidr)
            self._native = value
        return self._native


class GeneralName(Choice):
    _alternatives = [
        ('other_name', AnotherName, {'tag_type': 'implicit', 'tag': 0}),
        ('rfc822_name', IA5String, {'tag_type': 'implicit', 'tag': 1}),
        ('dns_name', IA5String, {'tag_type': 'implicit', 'tag': 2}),
        ('x400_address', ORAddress, {'tag_type': 'implicit', 'tag': 3}),
        ('directory_name', Name, {'tag_type': 'explicit', 'tag': 4}),
        ('edi_party_name', EDIPartyName, {'tag_type': 'implicit', 'tag': 5}),
        ('uniform_resource_identifier', IA5String, {'tag_type': 'implicit', 'tag': 6}),
        ('ip_address', IPAddress, {'tag_type': 'implicit', 'tag': 7}),
        ('registered_id', ObjectIdentifier, {'tag_type': 'implicit', 'tag': 8}),
    ]


class GeneralNames(SequenceOf):
    _child_spec = GeneralName


class Time(Choice):
    _alternatives = [
        ('utc_time', UTCTime),
        ('general_time', GeneralizedTime),
    ]


class Validity(Sequence):
    _fields = [
        ('not_before', Time),
        ('not_after', Time),
    ]


class BasicConstraints(Sequence):
    _fields = [
        ('ca', Boolean, {'default': False}),
        ('path_len_constraint', Integer, {'optional': True}),
    ]


class AuthorityKeyIdentifier(Sequence):
    _fields = [
        ('key_identifier', OctetString, {'tag_type': 'implicit', 'tag': 0, 'optional': True}),
        ('authority_cert_issuer', GeneralNames, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
        ('authority_cert_serial_number', Integer, {'tag_type': 'implicit', 'tag': 2, 'optional': True}),
    ]


class DistributionPointName(Choice):
    _alternatives = [
        ('full_name', GeneralNames, {'tag_type': 'implicit', 'tag': 0}),
        ('name_relative_to_crl_issuer', RelativeDistinguishedName, {'tag_type': 'implicit', 'tag': 1}),
    ]


class ReasonFlags(BitString):
    _map = {
        0: 'unused',
        1: 'key_compromise',
        2: 'ca_compromise',
        3: 'affiliation_changed',
        4: 'superseded',
        5: 'cessation_of_operation',
        6: 'certificate_hold',
        7: 'privilege_withdrawn',
        8: 'aa_compromise',
    }


class GeneralSubtree(Sequence):
    _fields = [
        ('base', GeneralName),
        ('minimum', Integer, {'tag_type': 'implicit', 'tag': 0, 'default': 0}),
        ('maximum', Integer, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
    ]


class GeneralSubtrees(SequenceOf):
    _child_spec = GeneralSubtree


class NameConstraints(Sequence):
    _fields = [
        ('permitted_subtrees', GeneralSubtrees, {'tag_type': 'implicit', 'tag': 0, 'optional': True}),
        ('excluded_subtrees', GeneralSubtrees, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
    ]


class DistributionPoint(Sequence):
    _fields = [
        ('distribution_point', DistributionPointName, {'tag_type': 'explicit', 'tag': 0, 'optional': True}),
        ('reasons', ReasonFlags, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
        ('crl_issuer', GeneralNames, {'tag_type': 'implicit', 'tag': 2, 'optional': True}),
    ]

    _url = False

    @property
    def url(self):
        """
        :return:
            None or a unicode string of the distribution point's URL
        """

        if self._url is False:
            self._url = None
            name = self['distribution_point']
            if name.name != 'full_name':
                raise ValueError('CRL distribution points that are relative to the issuer are not supported')

            for general_name in name.chosen:
                if general_name.name == 'uniform_resource_identifier':
                    url = general_name.native
                    if url[0:7] == 'http://':
                        self._url = url
                        break

        return self._url


class CRLDistributionPoints(SequenceOf):
    _child_spec = DistributionPoint


class DisplayText(Choice):
    _alternatives = [
        ('ia5_string', IA5String),
        ('visible_string', VisibleString),
        ('bmp_string', BMPString),
        ('utf8_string', UTF8String),
    ]


class NoticeNumbers(SequenceOf):
    _child_spec = Integer


class NoticeReference(Sequence):
    _fields = [
        ('organization', DisplayText),
        ('notice_numbers', NoticeNumbers),
    ]


class UserNotice(Sequence):
    _fields = [
        ('notice_ref', NoticeReference, {'optional': True}),
        ('explicit_text', DisplayText, {'optional': True}),
    ]


class PolicyQualifierId(ObjectIdentifier):
    _map = {
        '1.3.6.1.5.5.7.2.1': 'certification_practice_statement',
        '1.3.6.1.5.5.7.2.2': 'user_notice',
    }


class PolicyQualifierInfo(Sequence):
    _fields = [
        ('policy_qualifier_id', PolicyQualifierId),
        ('qualifier', Any),
    ]

    _oid_pair = ('policy_qualifier_id', 'qualifier')
    _oid_specs = {
        'certification_practice_statement': IA5String,
        'user_notice': UserNotice,
    }


class PolicyQualifierInfos(SequenceOf):
    _child_spec = PolicyQualifierInfo


class PolicyIdentifier(ObjectIdentifier):
    _map = {
        '2.5.29.32.0': 'any_policy',
    }


class PolicyInformation(Sequence):
    _fields = [
        ('policy_identifier', PolicyIdentifier),
        ('policy_qualifiers', PolicyQualifierInfos, {'optional': True})
    ]


class CertificatePolicies(SequenceOf):
    _child_spec = PolicyInformation


class PolicyMapping(Sequence):
    _fields = [
        ('issuer_domain_policy', ObjectIdentifier),
        ('subject_domain_policy', ObjectIdentifier),
    ]


class PolicyMappings(SequenceOf):
    _child_spec = PolicyMapping


class PolicyConstraints(Sequence):
    _fields = [
        ('require_explicit_policy', Integer, {'tag_type': 'implicit', 'tag': 0, 'optional': True}),
        ('inhibit_policy_mapping', Integer, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
    ]


class KeyPurposeId(ObjectIdentifier):
    _map = {
        '1.3.6.1.5.5.7.3.1': 'server_auth',
        '1.3.6.1.5.5.7.3.2': 'client_auth',
        '1.3.6.1.5.5.7.3.3': 'code_signing',
        '1.3.6.1.5.5.7.3.4': 'email_protection',
        '1.3.6.1.5.5.7.3.5': 'ipsec_end_system',
        '1.3.6.1.5.5.7.3.6': 'ipsec_tunnel',
        '1.3.6.1.5.5.7.3.7': 'ipsec_user',
        '1.3.6.1.5.5.7.3.8': 'time_stamping',
        '1.3.6.1.5.5.7.3.9': 'ocsp_signing',
        '1.3.6.1.5.5.7.3.19': 'wireless_access_points',
    }


class ExtKeyUsageSyntax(SequenceOf):
    _child_spec = KeyPurposeId


class AccessMethod(ObjectIdentifier):
    _map = {
        '1.3.6.1.5.5.7.48.1': 'ocsp',
        '1.3.6.1.5.5.7.48.2': 'ca_issuers',
        '1.3.6.1.5.5.7.48.3': 'time_stamping',
        '1.3.6.1.5.5.7.48.5': 'ca_repository',
    }


class AccessDescription(Sequence):
    _fields = [
        ('access_method', AccessMethod),
        ('access_location', GeneralName),
    ]


class AuthorityInfoAccessSyntax(SequenceOf):
    _child_spec = AccessDescription


class SubjectInfoAccessSyntax(SequenceOf):
    _child_spec = AccessDescription


class EntrustVersionInfo(Sequence):
    _fields = [
        ('entrust_vers', GeneralString),
        ('entrust_info_flags', BitString)
    ]


class NetscapeCertificateType(BitString):
    _map = {
        0: 'ssl_client',
        1: 'ssl_server',
        2: 'email',
        3: 'object_signing',
        4: 'reserved',
        5: 'ssl_ca',
        6: 'email_ca',
        7: 'object_signing_ca',
    }


class ExtensionId(ObjectIdentifier):
    _map = {
        '2.5.29.9': 'subject_directory_attributes',
        '2.5.29.14': 'key_identifier',
        '2.5.29.15': 'key_usage',
        '2.5.29.16': 'private_key_usage_period',
        '2.5.29.17': 'subject_alt_name',
        '2.5.29.18': 'issuer_alt_name',
        '2.5.29.19': 'basic_constraints',
        '2.5.29.23': 'hold_instruction_code',
        '2.5.29.30': 'name_constraints',
        '2.5.29.31': 'crl_distribution_points',
        '2.5.29.32': 'certificate_policies',
        '2.5.29.33': 'policy_mappings',
        '2.5.29.35': 'authority_key_identifier',
        '2.5.29.36': 'policy_constraints',
        '2.5.29.37': 'extended_key_usage',
        '2.5.29.46': 'freshest_crl',
        '2.5.29.54': 'inhibit_any_policy',
        '1.3.6.1.5.5.7.1.1': 'authority_information_access',
        '1.3.6.1.5.5.7.1.11': 'subject_information_access',
        '1.3.6.1.5.5.7.48.1.5': 'ocsp_no_check',
        '1.2.840.113533.7.65.0': 'entrust_version_extension',
        '2.16.840.1.113730.1.1': 'netscape_certificate_type',
    }


class Extension(Sequence):
    _fields = [
        ('extn_id', ExtensionId),
        ('critical', Boolean, {'default': False}),
        ('extn_value', OctetString),
    ]

    _oid_pair = ('extn_id', 'extn_value')
    _oid_specs = {
        'subject_directory_attributes': Attributes,
        'key_identifier': OctetString,
        'key_usage': KeyUsage,
        'private_key_usage_period': PrivateKeyUsagePeriod,
        'subject_alt_name': GeneralNames,
        'issuer_alt_name': GeneralNames,
        'basic_constraints': BasicConstraints,
        'hold_instruction_code': ObjectIdentifier,
        'name_constraints': NameConstraints,
        'crl_distribution_points': CRLDistributionPoints,
        'certificate_policies': CertificatePolicies,
        'policy_mappings': PolicyMappings,
        'authority_key_identifier': AuthorityKeyIdentifier,
        'policy_constraints': PolicyConstraints,
        'extended_key_usage': ExtKeyUsageSyntax,
        'freshest_crl': CRLDistributionPoints,
        'inhibit_any_policy': Integer,
        'authority_information_access': AuthorityInfoAccessSyntax,
        'subject_information_access': SubjectInfoAccessSyntax,
        'ocsp_no_check': Null,
        'entrust_version_extension': EntrustVersionInfo,
        'netscape_certificate_type': NetscapeCertificateType,
    }


class Extensions(SequenceOf):
    _child_spec = Extension


class Version(Integer):
    _map = {
        0: 'v1',
        1: 'v2',
        2: 'v3',
    }


class TbsCertificate(Sequence):
    _fields = [
        ('version', Version, {'tag_type': 'explicit', 'tag': 0, 'default': 'v1'}),
        ('serial_number', Integer),
        ('signature', SignedDigestAlgorithm),
        ('issuer', Name),
        ('validity', Validity),
        ('subject', Name),
        ('subject_public_key_info', PublicKeyInfo),
        ('issuer_unique_id', OctetBitString, {'tag_type': 'implicit', 'tag': 1, 'optional': True}),
        ('subject_unique_id', OctetBitString, {'tag_type': 'implicit', 'tag': 2, 'optional': True}),
        ('extensions', Extensions, {'tag_type': 'explicit', 'tag': 3, 'optional': True}),
    ]


class Certificate(Sequence):
    _fields = [
        ('tbs_certificate', TbsCertificate),
        ('signature_algorithm', SignedDigestAlgorithm),
        ('signature_value', OctetBitString),
    ]

    _processed_extensions = False
    _critical_extensions = None
    _subject_directory_attributes = None
    _key_identifier_value = None
    _key_usage_value = None
    _subject_alt_name_value = None
    _issuer_alt_name_value = None
    _basic_constraints_value = None
    _name_constraints_value = None
    _crl_distribution_points_value = None
    _certificate_policies_value = None
    _policy_mappings_value = None
    _authority_key_identifier_value = None
    _policy_constraints_value = None
    _freshest_crl_value = None
    _inhibit_any_policy_value = None
    _extended_key_usage_value = None
    _authority_information_access_value = None
    _subject_information_access_value = None
    _ocsp_no_check_value = None
    _issuer_serial = None
    _authority_issuer_serial = False
    _crl_distribution_points = None
    _delta_crl_distribution_points = None
    _valid_domains = None
    _valid_ips = None

    def _set_extensions(self):
        """
        Sets common named extensions to private attributes and creates a list
        of critical extensions
        """

        self._critical_extensions = []

        for extension in self['tbs_certificate']['extensions']:
            name = extension['extn_id'].native
            attribute_name = '_%s_value' % name
            if hasattr(self, attribute_name):
                setattr(self, attribute_name, extension['extn_value'].parsed)
            if extension['critical'].native:
                self._critical_extensions.append(name)

        self._processed_extensions = True

    @property
    def critical_extensions(self):
        """
        Returns a list of the names (or OID if not a known extension) of the
        extensions marked as critical

        :return:
            A list of unicode strings
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._critical_extensions

    @property
    def subject_directory_attributes_value(self):
        """
        This extension is used to contain additional identification attributes
        about the subject.

        :return:
            None or an Attributes object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._key_identifier_value

    @property
    def key_identifier_value(self):
        """
        This extension is used to help in creating certificate validation paths.
        It contains an identifier that should generally, but is not guaranteed
        to, be unique.

        :return:
            None or an OctetString object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._key_identifier_value

    @property
    def key_usage_value(self):
        """
        This extension is used to define the purpose of the public key
        contained within the certificate.

        :return:
            None or a KeyUsage
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._key_usage_value

    @property
    def subject_alt_name_value(self):
        """
        This extension allows for additional names to be associate with the
        subject of the certificate. While it may contain a whole host of
        possible names, it is usually used to allow certificates to be used
        with multiple different domain names.

        :return:
            None or a GeneralNames object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._subject_alt_name_value

    @property
    def issuer_alt_name_value(self):
        """
        This extension allows associating one or more alternative names with
        the issuer of the certificate.

        :return:
            None or an x509.GeneralNames object
        """

        if self._processed_extensions is False:
            self._processed_extensions()
        return self._issuer_alt_name_value

    @property
    def basic_constraints_value(self):
        """
        This extension is used to determine if the subject of the certificate
        is a CA, and if so, what the maximum number of intermediate CA certs
        after this are, before an end-entity certificate is found.

        :return:
            None or a BasicConstraints object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._basic_constraints_value

    @property
    def name_constraints_value(self):
        """
        This extension is used in CA certificates, and is used to limit the
        possible names of certificates issued.

        :return:
            None or a NameConstraints object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._name_constraints_value

    @property
    def crl_distribution_points_value(self):
        """
        This extension is used to help in locating the CRL for this certificate.

        :return:
            None or a CRLDistributionPoints object
            extension
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._crl_distribution_points_value

    @property
    def certificate_policies_value(self):
        """
        This extension defines policies in CA certificates under which
        certificates may be issued. In end-entity certificates, the inclusion
        of a policy indicates the issuance of the certificate follows the
        policy.

        :return:
            None or a CertificatePolicies object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._certificate_policies_value

    @property
    def policy_mappings_value(self):
        """
        This extension allows mapping policy OIDs to other OIDs. This is used
        to allow different policies to be treated as equivalent in the process
        of validation.

        :return:
            None or a PolicyMappings object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._policy_mappings_value

    @property
    def authority_key_identifier_value(self):
        """
        This extension helps in identifying the public key with which to
        validate the authenticity of the certificate.

        :return:
            None or an AuthorityKeyIdentifier object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._authority_key_identifier_value

    @property
    def policy_constraints_value(self):
        """
        This extension is used to control if policy mapping is allowed and
        when policies are required.

        :return:
            None or a PolicyConstraints object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._policy_constraints_value

    @property
    def freshest_crl_value(self):
        """
        This extension is used to help locate any available delta CRLs

        :return:
            None or an CRLDistributionPoints object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._freshest_crl_value

    @property
    def inhibit_any_policy_value(self):
        """
        This extension is used to prevent mapping of the any policy to
        specific requirements

        :return:
            None or a Integer object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._inhibit_any_policy_value

    @property
    def extended_key_usage_value(self):
        """
        This extension is used to define additional purposes for the public key
        beyond what is contained in the basic constraints.

        :return:
            None or an ExtKeyUsageSyntax object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._extended_key_usage_value

    @property
    def authority_information_access_value(self):
        """
        This extension is used to locate the CA certificate used to sign this
        certificate, or the OCSP responder for this certificate.

        :return:
            None or an AuthorityInfoAccessSyntax object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._authority_information_access_value

    @property
    def subject_information_access_value(self):
        """
        This extension is used to access information about the subject of this
        certificate.

        :return:
            None or a SubjectInfoAccessSyntax object
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._subject_information_access_value

    @property
    def ocsp_no_check_value(self):
        """
        This extension is used on certificates of OCSP responders, indicating
        that revocation information for the certificate should never need to
        be verified, thus preventing possible loops in path validation.

        :return:
            None or a Null object (if present)
        """

        if not self._processed_extensions:
            self._set_extensions()
        return self._ocsp_no_check_value

    @property
    def public_key(self):
        """
        :return:
            The PublicKeyInfo object for this certificate
        """

        return self['tbs_certificate']['subject_public_key_info']

    @property
    def subject(self):
        """
        :return:
            The Name object for the subject of this certificate
        """

        return self['tbs_certificate']['subject']

    @property
    def issuer(self):
        """
        :return:
            The Name object for the issuer of this certificate
        """

        return self['tbs_certificate']['issuer']

    @property
    def serial_number(self):
        """
        :return:
            An integer of the certificate's serial number
        """

        return self['tbs_certificate']['serial_number'].native

    @property
    def key_identifier(self):
        """
        :return:
            None or a byte string of the certificate's key identifier from the
            key identifier extension
        """

        if not self.key_identifier_value:
            return None

        return self.key_identifier_value.native

    @property
    def issuer_serial(self):
        """
        :return:
            A byte string of the SHA-256 hash of the issuer concatenated with
            the ascii character ":", concatenated with the serial number as
            an ascii string
        """

        if self._issuer_serial is None:
            self._issuer_serial = self.issuer.sha256 + b':' + str_cls(self.serial_number).encode('ascii')
        return self._issuer_serial

    @property
    def authority_key_identifier(self):
        """
        :return:
            None or a byte string of the key_identifier from the authority key
            identifier extension
        """

        if not self.authority_key_identifier_value:
            return None

        return self.authority_key_identifier_value['key_identifier'].native

    @property
    def authority_issuer_serial(self):
        """
        :return:
            None or a byte string of the SHA-256 hash of the isser from the
            authority key identifier extension concatenated with the ascii
            character ":", concatenated with the serial number from the
            authority key identifier extension as an ascii string
        """

        if self._authority_issuer_serial is False:
            if self.authority_key_identifier_value and self.authority_key_identifier_value['authority_cert_issuer'].native:
                authority_issuer = self.authority_key_identifier_value['authority_cert_issuer'][0].chosen
                # We untag the element since it is tagged via being a choice from GeneralName
                authority_issuer = authority_issuer.untag()
                authority_serial = self.authority_key_identifier_value['authority_cert_serial_number'].native
                self._authority_issuer_serial = authority_issuer.sha256 + b':' + str_cls(authority_serial).encode('ascii')
            else:
                self._authority_issuer_serial = None
        return self._authority_issuer_serial

    @property
    def crl_distribution_points(self):
        """
        Returns complete CRL URLs - does not include delta CRLs

        :return:
            A list of zero or more DistributionPoint objects
        """

        if self._crl_distribution_points is None:
            self._crl_distribution_points = self._get_http_crl_distribution_points(self.crl_distribution_points_value)
        return self._crl_distribution_points

    @property
    def delta_crl_distribution_points(self):
        """
        Returns delta CRL URLs - does not include complete CRLs

        :return:
            A list of zero or more DistributionPoint objects
        """

        if self._delta_crl_distribution_points is None:
            self._delta_crl_distribution_points = self._get_http_crl_distribution_points(self.freshest_crl_value)
        return self._delta_crl_distribution_points

    def _get_http_crl_distribution_points(self, crl_distribution_points):
        """
        Fetches the DistributionPoint object for non-relative, HTTP CRLs
        referenced by the certificate

        :param crl_distribution_points:
            A CRLDistributionPoints object to grab the DistributionPoints from

        :return:
            A list of zero or more DistributionPoint objects
        """

        output = []

        if crl_distribution_points is None:
            return []

        for distribution_point in crl_distribution_points:
            distribution_point_name = distribution_point['distribution_point']
            # RFC5280 indicates conforming CA should not use the relative form
            if distribution_point_name.name == 'name_relative_to_crl_issuer':
                continue
            # This library is currently only concerned with HTTP-based CRLs
            for general_name in distribution_point_name.chosen:
                if general_name.name == 'uniform_resource_identifier':
                    output.append(distribution_point)

        return output

    @property
    def ocsp_urls(self):
        """
        :return:
            A list of zero or more unicode strings of the OCSP URLs for this
            cert
        """

        if not self.authority_information_access_value:
            return []

        output = []
        for entry in self.authority_information_access_value:
            if entry['access_method'].native == 'ocsp':
                location = entry['access_location']
                if location.name != 'uniform_resource_identifier':
                    continue
                url = location.native
                if url.lower()[0:7] == 'http://':
                    output.append(url)
        return output

    @property
    def valid_domains(self):
        """
        :return:
            A list of unicode strings of valid domain names for the certificate.
            Wildcard certificates will have a domain in the form: *.example.com
        """

        if self._valid_domains is None:
            self._valid_domains = []

            # If the common name in the subject looks like a domain, add it
            pattern = re.compile('^(\\*\\.)?(?:[a-zA-Z0-9](?:[a-zA-Z0-9\\-]*[a-zA-Z0-9])?\\.)+[a-zA-Z]{2,}$')
            for rdn in self.subject.chosen:
                for name_type_value in rdn:
                    if name_type_value['type'].native == 'common_name':
                        value = name_type_value['value'].native
                        if pattern.match(value):
                            self._valid_domains.append(value)

            # For the subject alt name extension, we can look at the name of
            # the choice selected since it distinguishes between domain names,
            # email addresses, IPs, etc
            if self.subject_alt_name_value:
                for general_name in self.subject_alt_name_value:
                    if general_name.name == 'dns_name' and general_name.native not in self._valid_domains:
                        self._valid_domains.append(general_name.native)

        return self._valid_domains

    @property
    def valid_ips(self):
        """
        :return:
            A list of unicode strings of valid IP addresses for the certificate
        """

        if self._valid_ips is None:
            self._valid_ips = []

            if self.subject_alt_name_value:
                for general_name in self.subject_alt_name_value:
                    if general_name.name == 'ip_address':
                        self._valid_ips.append(general_name.native)

        return self._valid_ips
