import hashlib
import io
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Sequence, Union, NamedTuple, Optional, Tuple, Dict

import pkginfo
from pkginfo import distribution


class InvalidDistribution(Exception):
    """Raised when a distribution is invalid."""
    pass


class InvalidSigningExecutable(Exception):
    """Signing executable must be installed on system."""
    pass


class WinInst(distribution.Distribution):
    def __init__(self, filename: str, metadata_version: Optional[str] = None) -> None:
        self.filename = filename
        self.metadata_version = metadata_version
        self.extractMetadata()
    
    def read(self) -> bytes:
        fqn = os.path.abspath(os.path.normpath(self.filename))
        if not os.path.exists(fqn):
            raise InvalidDistribution(f'No such file: {fqn}')
        
        if fqn.endswith('.exe'):
            archive = zipfile.ZipFile(fqn)
            names = archive.namelist()
            
            def read_file(name: str) -> bytes:
                return archive.read(name)
        
        else:
            raise InvalidDistribution(f'Not a known archive format for file: {fqn}')
        
        try:
            tuples = [x.split('/') for x in names if x.endswith('.egg-info') or x.endswith('PKG-INFO')]
            schwarz = sorted([(len(x), x) for x in tuples])
            for path in [x[1] for x in schwarz]:
                candidate = '/'.join(path)
                data = read_file(candidate)
                if b'Metadata-Version' in data:
                    return data
        finally:
            archive.close()
        
        raise InvalidDistribution(f'No PKG-INFO/.egg-info in archive: {fqn}')


DIST_TYPES = {
    'bdist_wheel':   pkginfo.Wheel,
    'bdist_wininst': WinInst,
    'bdist_egg':     pkginfo.BDist,
    'sdist':         pkginfo.SDist,
}

DIST_EXTENSIONS = {
    '.whl':     'bdist_wheel',
    '.exe':     'bdist_wininst',
    '.egg':     'bdist_egg',
    '.tar.bz2': 'sdist',
    '.tar.gz':  'sdist',
    '.zip':     'sdist',
}

DIST_VERSION = {
    'bdist_wheel':   re.compile((
        r'^(?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)'
        r'((-(?P<build>\d.*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)'
        r'\.whl|\.dist-info)$'
    ), re.VERBOSE),
    'bdist_wininst': re.compile(r'.*py(?P<pyver>\d+\.\d+)\.exe$'),
    'bdist_egg':     re.compile((
        r'^(?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)'
        r'((-(?P<build>\d.*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)'
        r'\.egg|\.egg-info)$'
    ), re.VERBOSE),
}

MetadataValue = Union[str, Sequence[str]]


def _safe_name(name: str) -> str:
    """Convert an arbitrary string to a standard distribution name.

    Any runs of non-alphanumeric/. characters are replaced with a single '-'.

    Copied from pkg_resources.safe_name for compatibility with warehouse.
    See https://github.com/pypa/twine/issues/743.
    """
    return re.sub('[^A-Za-z0-9.]+', '-', name)


class Package:
    def __init__(self, file: Path, comment: Optional[str]):
        self.file: Path = file
        self.comment: Optional[str] = comment
        
        # self.metadata = metadata
        self.file_type: Optional[str] = None
        for ext, file_type in DIST_EXTENSIONS.items():
            if self.file.name.endswith(ext):
                try:
                    self.metadata = DIST_TYPES[file_type](self.file)  # Convert to str?
                except EOFError:
                    raise InvalidDistribution(f'Invalid distribution file: \'{self.file.name}\'')
                else:
                    self.file_type = file_type
                    break
        else:
            raise InvalidDistribution(f'Unknown distribution format: \'{self.file.name}\'')
        
        # If pkginfo encounters a metadata version it doesn't support, it may
        # give us back empty metadata. At the very least, we should have a name
        # and version
        if not (self.metadata.name and self.metadata.version):
            supported_metadata = list(pkginfo.distribution.HEADER_ATTRS)
            raise InvalidDistribution(
                'Invalid distribution metadata. '
                'This version of twine supports Metadata-Version '
                f'{", ".join(supported_metadata[:-1])}, and {supported_metadata[-1]}'
            )
        
        self.python_version: Optional[str] = None
        if self.file_type in DIST_VERSION:
            self.python_version = 'any'
            if (m := DIST_VERSION[self.file_type].match(self.file.name)) is not None:
                self.python_version = m.group('pyver')
        
        self.safe_name: str = _safe_name(self.metadata.name)
        self.signed_file = self.file.with_name(self.file.name + '.asc')
        self.gpg_signature: Optional[Tuple[str, bytes]] = None
        
        hasher = HashManager(self.file)
        hasher.hash()
        hexdigest = hasher.hexdigest()
        
        self.md5_digest = hexdigest.md5
        self.sha2_digest = hexdigest.sha2
        self.blake2_256_digest = hexdigest.blake2
    
    def metadata_dictionary(self) -> Dict[str, MetadataValue]:
        """Merge multiple sources of metadata into a single dictionary.

        Includes values from filename, PKG-INFO, hashers, and signature.
        """
        meta = self.metadata
        data = {
            # identify release
            'name':                     self.safe_name,
            'version':                  meta.version,
            # file content
            'filetype':                 self.file_type,
            'pyversion':                self.python_version,
            # additional meta-data
            'metadata_version':         meta.metadata_version,
            'summary':                  meta.summary,
            'home_page':                meta.home_page,
            'author':                   meta.author,
            'author_email':             meta.author_email,
            'maintainer':               meta.maintainer,
            'maintainer_email':         meta.maintainer_email,
            'license':                  meta.license,
            'description':              meta.description,
            'keywords':                 meta.keywords,
            'platform':                 meta.platforms,
            'classifiers':              meta.classifiers,
            'download_url':             meta.download_url,
            'supported_platform':       meta.supported_platforms,
            'comment':                  self.comment,
            'sha256_digest':            self.sha2_digest,
            # PEP 314
            'provides':                 meta.provides,
            'requires':                 meta.requires,
            'obsoletes':                meta.obsoletes,
            # Metadata 1.2
            'project_urls':             meta.project_urls,
            'provides_dist':            meta.provides_dist,
            'obsoletes_dist':           meta.obsoletes_dist,
            'requires_dist':            meta.requires_dist,
            'requires_external':        meta.requires_external,
            'requires_python':          meta.requires_python,
            # Metadata 2.1
            'provides_extras':          meta.provides_extras,
            'description_content_type': meta.description_content_type,
            # Metadata 2.2
            'dynamic':                  meta.dynamic,
        }
        
        if self.gpg_signature is not None:
            data['gpg_signature'] = self.gpg_signature
        
        # FIPS disables MD5 and Blake2, making the digest values None. Some package
        # repositories don't allow null values, so this only sends non-null values.
        # See also: https://github.com/pypa/twine/issues/775
        if self.md5_digest:
            data['md5_digest'] = self.md5_digest
        
        if self.blake2_256_digest:
            data['blake2_256_digest'] = self.blake2_256_digest
        
        return data
    
    def add_gpg_signature(self, signature_file: Path) -> None:
        if self.gpg_signature is not None:
            raise InvalidDistribution('GPG Signature can only be added once')
        
        with signature_file.open('rb') as gpg:
            self.gpg_signature = (signature_file.name, gpg.read())
    
    def sign(self, sign_with: str, identity: Optional[str]) -> None:
        print(f'Signing {self.file.name}')
        gpg_args: Tuple[str, ...] = (sign_with, '--detach-sign')
        if identity:
            gpg_args += ('--local-user', identity)
        gpg_args += ('-a', str(self.file.absolute()))
        self.run_gpg(gpg_args)
        
        self.add_gpg_signature(self.signed_file)
    
    @classmethod
    def run_gpg(cls, gpg_args: Tuple[str, ...]) -> None:
        try:
            subprocess.check_call(gpg_args)
            return
        except FileNotFoundError:
            if gpg_args[0] != 'gpg':
                raise InvalidSigningExecutable(f'{gpg_args[0]} executable not available.')
        
        print('gpg executable not available. Attempting fallback to gpg2.')
        try:
            subprocess.check_call(('gpg2',) + gpg_args[1:])
        except FileNotFoundError:
            print('gpg2 executable not available.')
            raise InvalidSigningExecutable(
                '\'gpg\' or \'gpg2\' executables not available. '
                'Try installing one of these or specifying an executable '
                'with the --sign-with flag.'
            )


class HexDigest(NamedTuple):
    md5: Optional[str]
    sha2: Optional[str]
    blake2: Optional[str]


class HashManager:
    """Manage our hashing objects for simplicity.

    This will also allow us to better test this logic.
    """
    
    def __init__(self, file: Path) -> None:
        """Initialize our manager and hasher objects."""
        self.file = file
        
        self._md5_hasher = None
        try:
            self._md5_hasher = hashlib.md5()
        except ValueError:
            # FIPs mode disables MD5
            pass
        
        self._sha2_hasher = hashlib.sha256()
        
        self._blake_hasher = None
        try:
            self._blake_hasher = hashlib.blake2b(digest_size=256 // 8)
        except ValueError:
            # FIPS mode disables blake2
            pass
    
    def _md5_update(self, content: bytes) -> None:
        if self._md5_hasher is not None:
            self._md5_hasher.update(content)
    
    def _md5_hexdigest(self) -> Optional[str]:
        if self._md5_hasher is not None:
            return self._md5_hasher.hexdigest()
        return None
    
    def _sha2_update(self, content: bytes) -> None:
        if self._sha2_hasher is not None:
            self._sha2_hasher.update(content)
    
    def _sha2_hexdigest(self) -> Optional[str]:
        if self._sha2_hasher is not None:
            return self._sha2_hasher.hexdigest()
        return None
    
    def _blake_update(self, content: bytes) -> None:
        if self._blake_hasher is not None:
            self._blake_hasher.update(content)
    
    def _blake_hexdigest(self) -> Optional[str]:
        if self._blake_hasher is not None:
            return self._blake_hasher.hexdigest()
        return None
    
    def hash(self) -> None:
        """Hash the file contents."""
        with self.file.open('rb') as fp:
            for content in iter(lambda: fp.read(io.DEFAULT_BUFFER_SIZE), b''):
                self._md5_update(content)
                self._sha2_update(content)
                self._blake_update(content)
    
    def hexdigest(self) -> HexDigest:
        """Return the hexdigest for the file."""
        return HexDigest(
            self._md5_hexdigest(),
            self._sha2_hexdigest(),
            self._blake_hexdigest(),
        )
