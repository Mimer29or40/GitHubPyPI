from __future__ import annotations

import email.utils
import re
from cgi import parse_header
from dataclasses import dataclass, field, fields
from typing import Any, Union, Optional, get_args, get_origin

import packaging.requirements
import packaging.specifiers
import packaging.version
from rfc3986 import uri_reference, exceptions, validators
from trove_classifiers import classifiers, deprecated_classifiers

_legacy_specifier_re = re.compile(r'^(?P<name>\S+)(?: \((?P<specifier>\S+)\))?$')


def _validate_pep440_version(name, value) -> None:
    parsed = packaging.version.parse(value)
    
    # Check that this version is a valid PEP 440 version at all.
    if not isinstance(parsed, packaging.version.Version):
        raise ValueError(
            f'metadata provided wrong value for \'{name}\'. '
            'Start and end with a letter or numeral containing only '
            'ASCII numeric and \'.\', \'_\' and \'-\'.'
        )
    
    # Check that this version does not have a PEP 440 local segment attached
    # to it.
    if parsed.local is not None:
        raise ValueError(
            f'metadata provided wrong value for \'{name}\'. '
            'Can\'t use PEP 440 local versions.'
        )


def _validate_description_content_type(name, value):
    def _raise(message):
        raise ValueError(f'Invalid description content type: {message}')
    
    content_type, parameters = parse_header(value)
    if content_type not in {'text/plain', 'text/x-rst', 'text/markdown'}:
        _raise('type/subtype is not valid')
    
    charset = parameters.get('charset')
    if charset and charset != 'UTF-8':
        _raise('Use a valid charset')
    
    valid_markdown_variants = {'CommonMark', 'GFM'}
    
    variant = parameters.get('variant')
    if content_type == 'text/markdown' and variant and variant not in valid_markdown_variants:
        _raise(f'Use a valid variant, expected one of {", ".join(valid_markdown_variants)}')


def _validate_rfc822_email_field(name, value):
    email_validator = Email(message=f'Use a valid email address for \'{name}\'')
    addresses = email.utils.getaddresses([value])
    
    for real_name, address in addresses:
        email_validator(name, address)


def _validate_no_deprecated_classifiers(name, value):
    invalid_classifiers = set(value or []) & deprecated_classifiers.keys()
    if invalid_classifiers:
        first_invalid_classifier_name = sorted(invalid_classifiers)[0]
        deprecated_by = deprecated_classifiers[first_invalid_classifier_name]
        
        if deprecated_by:
            raise ValueError(
                f'Classifier {first_invalid_classifier_name!r} has been '
                'deprecated, use the following classifier(s) instead: '
                f'{deprecated_by}'
            )
        else:
            raise ValueError(f'Classifier {first_invalid_classifier_name!r} has been deprecated.')


def _validate_classifiers(name, value):
    invalid = sorted(set(value or []) - classifiers)
    
    if invalid:
        if len(invalid) == 1:
            raise ValueError(f'Classifier {invalid[0]!r} is not a valid classifier.')
        else:
            raise ValueError(f'Classifiers {invalid!r} are not valid classifiers.')


def _validate_pep440_specifier_field(name, value):
    try:
        packaging.specifiers.SpecifierSet(value)
    except packaging.specifiers.InvalidSpecifier:
        raise ValueError('Invalid specifier in requirement.') from None


def _validate_legacy_non_dist_req_list(name, value):
    for datum in value:
        try:
            req = packaging.requirements.Requirement(datum.replace('_', ''))
        except packaging.requirements.InvalidRequirement:
            raise ValueError('Invalid requirement: {!r}'.format(datum)) from None
        
        if req.url is not None:
            raise ValueError('Can\'t direct dependency: {!r}'.format(datum))
        
        if any(not identifier.isalnum() or identifier[0].isdigit() for identifier in req.name.split('.')):
            raise ValueError('Use a valid Python identifier.')


def _validate_legacy_dist_req_list(name, value):
    for datum in value:
        try:
            req = packaging.requirements.Requirement(datum)
        except packaging.requirements.InvalidRequirement:
            raise ValueError('Invalid requirement: {!r}.'.format(datum)) from None
        
        if req.url is not None:
            raise ValueError('Can\'t have direct dependency: {!r}'.format(datum))


def _validate_pep440_specifier(specifier):
    try:
        packaging.specifiers.SpecifierSet(specifier)
    except packaging.specifiers.InvalidSpecifier:
        raise ValueError('Invalid specifier in requirement.') from None


def _validate_requires_external_list(name, value):
    for datum in value:
        parsed = _legacy_specifier_re.search(datum)
        if parsed is None:
            raise ValueError('Invalid requirement.')
        name, specifier = parsed.groupdict()['name'], parsed.groupdict()['specifier']
        
        # TODO: Is it really reasonable to parse the specifier using PEP 440?
        if specifier is not None:
            _validate_pep440_specifier(specifier)


def _validate_project_url_list(name, value):
    for datum in value:
        try:
            label, url = datum.split(', ', 1)
        except ValueError:
            raise ValueError('Use both a label and an URL.') from None
        
        if not label:
            raise ValueError('Use a label.')
        
        if len(label) > 32:
            raise ValueError('Use 32 characters or less.')
        
        if not url:
            raise ValueError('Use an URL.')
        
        if not is_valid_uri(str(url), require_authority=False):
            raise ValueError('Use valid URL.')


def is_valid_uri(uri, require_scheme: bool = True, allowed_schemes: list[str] = None, require_authority: bool = True):
    if allowed_schemes is None:
        allowed_schemes = ['http', 'https']
    
    uri = uri_reference(uri).normalize()
    validator = validators.Validator().allow_schemes(*allowed_schemes)
    if require_scheme:
        validator.require_presence_of('scheme')
    if require_authority:
        validator.require_presence_of('host')
    
    validator.check_validity_of('scheme', 'host', 'port', 'path', 'query')
    
    try:
        validator.validate(uri)
    except exceptions.ValidationError:
        return False
    
    return True


class Validator:
    def __init__(self, message: str = ''):
        self.message = message
    
    def __call__(self, name: str, value: Any) -> None:
        raise ValueError(self.message)


class Length(Validator):
    def __init__(self, max: int, message: str = 'metadata provided wrong value for \'{name}\'. length must be <={max}'):
        super().__init__(message)
        self.max: int = max
    
    def __call__(self, name: str, value: Any) -> None:
        if len(value) > self.max:
            raise ValueError(self.message.format(name=name, max=self.max))


class AnyOf(Validator):
    def __init__(self, values: list[Any], message: str = 'metadata provided wrong value for \'{name}\'. must be in {values}'):
        super().__init__(message)
        self.values: list[Any] = list(values)
    
    def __call__(self, name: str, value: Any) -> None:
        if value not in self.values:
            raise ValueError(self.message.format(name=name, value=list(map(str, self.values))))


class RegExp(Validator):
    def __init__(self, pattern: str, flags: Union[int, re.RegexFlag] = 0, message: str = 'metadata provided wrong value for \'{name}\'. must match {pattern}'):
        super().__init__(message)
        self.pattern: str = pattern
        self.flags: Union[int, re.RegexFlag] = flags
    
    def __call__(self, name: str, value: Any) -> None:
        if re.match(self.pattern, value, self.flags) is None:
            raise ValueError(self.message.format(name=name, pattern=self.pattern))


class Email(Validator):
    _pattern = re.compile((
        r'([a-z0-9!#$%&\'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&\'*+/=?^_`{|}~-]+)*|"'
        r'(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")'
        r'@((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?'
        r'|\[(?:(?:2(?:5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])\.){3}'
        r'(?:(?:2(?:5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:'
        r'(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)])'
    ), re.IGNORECASE)
    
    def __init__(self, message: str = 'metadata provided wrong value for \'{name}\'. must be valid email'):
        super().__init__(message)
    
    def __call__(self, name: str, value: Any) -> None:
        if self._pattern.match(value) is None:
            raise ValueError(self.message.format(name=name))


class URI:
    def __init__(self, require_scheme: bool = True, allowed_schemes: list[str] = None, require_authority: bool = True):
        self.require_scheme: bool = require_scheme
        self.allowed_schemes: list[str] = ['http', 'https'] if allowed_schemes is None else allowed_schemes
        self.require_authority: bool = require_authority
    
    def __call__(self, name, value):
        if not is_valid_uri(
                str(value),
                require_authority=self.require_authority,
                allowed_schemes=self.allowed_schemes,
                require_scheme=self.require_scheme,
        ):
            raise ValueError(f'Invalid URI \'{value}\'')


@dataclass
class MetadataForm:
    # Metadata version
    metadata_version: str = field(repr=False, metadata={
        'description': 'Metadata-Version',
        'validators':  [
            AnyOf(
                # Note: This isn't really Metadata 2.0, however bdist_wheel
                #       claims it is producing a Metadata 2.0 metadata when in
                #       reality it's more like 1.2 with some extensions.
                ['1.0', '1.1', '1.2', '2.0', '2.1'],
                message='Use a known metadata version.',
            )
        ]
    })
    
    # Identity Project and Release
    name: str = field(repr=False, metadata={
        'description': 'Name',
        'validators':  [
            RegExp(
                r'^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$',
                re.IGNORECASE,
                message=(
                    'Start and end with a letter or numeral containing '
                    'only ASCII numeric and \'.\', \'_\' and \'-\'.'
                )
            )
        ]
    })
    
    version: str = field(repr=False, metadata={
        'description': 'Version',
        'validators':  [
            RegExp(
                r'^(?!\s).*(?<!\s)$',
                message='Can\'t have leading or trailing whitespace.',
            ),
            _validate_pep440_version,
        ]
    })
    
    # Additional Release metadata
    summary: Optional[str] = field(repr=False, metadata={
        'description': 'Summary',
        'validators':  [
            Length(max=512),
            RegExp(
                r'^.+$',  # Rely on the fact that . doesn't match a newline.
                message='Use a single line only.',
            )
        ]
    })
    
    description: Optional[str] = field(repr=False, metadata={
        'description': 'Description',
        'validators':  []
    })
    
    author: Optional[str] = field(repr=False, metadata={
        'description': 'Author'
    })
    
    description_content_type: Optional[str] = field(repr=False, metadata={
        'description': 'Description-Content-Type',
        'validators':  [_validate_description_content_type]
    })
    
    author_email: Optional[str] = field(repr=False, metadata={
        'description': 'Author-email',
        'validators':  [_validate_rfc822_email_field]
    })
    
    maintainer: Optional[str] = field(repr=False, metadata={
        'description': 'Maintainer'
    })
    
    maintainer_email: Optional[str] = field(repr=False, metadata={
        'description': 'Maintainer-email',
        'validators':  [_validate_rfc822_email_field],
    })
    
    license: Optional[str] = field(repr=False, metadata={
        'description': 'License', 'validators': []
    })
    
    keywords: Optional[str] = field(repr=False, metadata={
        'description': 'Keywords', 'validators': []
    })
    
    classifiers: list = field(repr=False, metadata={
        'description': 'Classifier',
        'validators':  [_validate_no_deprecated_classifiers, _validate_classifiers],
    })
    
    platform: Optional[str] = field(repr=False, metadata={
        'description': 'Platform', 'validators': []
    })
    
    home_page: Optional[str] = field(repr=False, metadata={
        'description': 'Home-Page',
        'validators':  [URI()],
    })
    
    download_url: Optional[str] = field(repr=False, metadata={
        'description': 'Download-URL',
        'validators':  [URI()],
    })
    
    requires_python: Optional[str] = field(repr=False, metadata={
        'description': 'Requires-Python',
        'validators':  [_validate_pep440_specifier_field],
    })
    
    pyversion: Optional[str] = field(repr=False, metadata={
        'validators': []
    })
    
    filetype: str = field(repr=False, metadata={
        'validators': [
            AnyOf(['bdist_egg', 'bdist_wheel', 'sdist'], message='Use a known file type.'),
        ]
    })
    
    comment: Optional[str] = field(repr=False, metadata={
        'validators': []
    })
    
    md5_digest: Optional[str] = field(repr=False, metadata={
        'validators': []
    })
    
    sha256_digest: Optional[str] = field(repr=False, metadata={
        'validators': [
            RegExp(
                r'^[A-F0-9]{64}$',
                re.IGNORECASE,
                message='Use a valid, hex-encoded, SHA256 message digest.',
            ),
        ]
    })
    
    blake2_256_digest: Optional[str] = field(repr=False, metadata={
        'validators': [
            RegExp(
                r'^[A-F0-9]{64}$',
                re.IGNORECASE,
                message='Use a valid, hex-encoded, BLAKE2 message digest.',
            ),
        ]
    })
    
    requires: Optional[list] = field(repr=False, metadata={
        'validators': [_validate_legacy_non_dist_req_list]
    })
    
    provides: Optional[list] = field(repr=False, metadata={
        'validators': [_validate_legacy_non_dist_req_list]
    })
    
    obsoletes: Optional[list] = field(repr=False, metadata={
        'validators': [_validate_legacy_non_dist_req_list]
    })
    
    requires_dist: Optional[list] = field(repr=False, metadata={
        'description': 'Requires-Dist',
        'validators':  [_validate_legacy_dist_req_list],
    })
    
    provides_dist: Optional[list] = field(repr=False, metadata={
        'description': 'Provides-Dist',
        'validators':  [_validate_legacy_dist_req_list],
    })
    
    obsoletes_dist: Optional[list] = field(repr=False, metadata={
        'description': 'Obsoletes-Dist',
        'validators':  [_validate_legacy_dist_req_list],
    })
    
    requires_external: Optional[list] = field(repr=False, metadata={
        'description': 'Requires-External',
        'validators':  [_validate_requires_external_list],
    })
    
    project_urls: Optional[list] = field(repr=False, metadata={
        'description': 'Project-URL',
        'validators':  [_validate_project_url_list],
    })
    
    @classmethod
    def from_kwargs(cls, **kwargs):
        # fetch the constructor's signature
        cls_fields = {field.name for field in fields(cls)}
        
        # split the kwargs into native ones and new ones
        native_args, new_args = {}, {}
        for name, val in kwargs.items():
            if name in cls_fields:
                native_args[name] = val
            else:
                new_args[name] = val
        
        # use the native ones to create the class ...
        ret = cls(**native_args)
        
        # ... and add the new ones by hand
        for new_name, new_val in new_args.items():
            setattr(ret, new_name, new_val)
        
        return ret
    
    def __post_init__(self):
        def extract_type(type_str):
            _type = eval(type_str)
            types = get_args(_type)
            optional = get_origin(_type) is Union and type(None) in types
            return optional, types[0] if optional else _type
        
        for field in fields(self):
            optional, field_type = extract_type(field.type)
            value = getattr(self, field.name)
            if value is None:
                if optional:
                    continue
                else:
                    raise ValueError(f'missing required field for \'{field.name}\'')
            elif not isinstance(value, field_type):
                value = field_type(value)
                setattr(self, field.name, value)
            for validator in field.metadata.get('validators', []):
                validator(field.name, value)
        
        # All non source releases *must* have a pyversion
        if self.filetype and self.filetype != 'sdist' and not self.pyversion:
            raise ValueError('Python version is required for binary distribution uploads.')
        
        # All source releases *must* have a pyversion of 'source'
        if self.filetype == 'sdist':
            if not self.pyversion:
                self.pyversion = 'source'
            elif self.pyversion != 'source':
                raise ValueError('Use \'source\' as Python version for an sdist.')
        
        # We *must* have at least one digest to verify against.
        if not self.md5_digest and not self.sha256_digest:
            raise ValueError('Include at least one message digest.')
