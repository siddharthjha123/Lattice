"""Owner-private files: POSIX permissions or protected Windows user/SYSTEM ACLs."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path

WINDOWS = os.name == "nt"


def reject_link(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Private path cannot be a symlink")
    if path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
    ):
        raise ValueError("Private path cannot be a Windows reparse point")


def windows_security():
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    return win32security, sid


def assert_windows_descriptor(descriptor):
    security, sid = windows_security()
    if security.ConvertSidToStringSid(
        descriptor.GetSecurityDescriptorOwner()
    ) != security.ConvertSidToStringSid(sid):
        raise PermissionError("Private file must belong to the current Windows user")
    acl = descriptor.GetSecurityDescriptorDacl()
    if acl is None:
        raise PermissionError("Private file has an unrestricted Windows DACL")
    permitted = {
        security.ConvertSidToStringSid(sid),
        security.ConvertSidToStringSid(
            security.CreateWellKnownSid(security.WinLocalSystemSid, None)
        ),
    }
    for index in range(acl.GetAceCount()):
        ace = acl.GetAce(index)
        # Deny ACEs cannot grant another identity access. Object/callback ACEs
        # are rejected rather than guessing their access semantics.
        if ace[0][0] == security.ACCESS_DENIED_ACE_TYPE:
            continue
        if (
            ace[0][0] != security.ACCESS_ALLOWED_ACE_TYPE
            or security.ConvertSidToStringSid(ace[-1]) not in permitted
        ):
            raise PermissionError("Private file grants access beyond its owner/SYSTEM")


def make_private(path, *, directory=False):
    path = Path(path)
    reject_link(path)
    if WINDOWS:
        import ntsecuritycon

        security, sid = windows_security()
        before = security.GetNamedSecurityInfo(
            str(path), security.SE_FILE_OBJECT, security.OWNER_SECURITY_INFORMATION
        )
        if security.ConvertSidToStringSid(
            before.GetSecurityDescriptorOwner()
        ) != security.ConvertSidToStringSid(sid):
            raise PermissionError("Refusing to change another Windows user's file")
        acl = security.ACL()
        flags = (
            security.OBJECT_INHERIT_ACE | security.CONTAINER_INHERIT_ACE
            if directory
            else 0
        )
        for principal in (
            sid,
            security.CreateWellKnownSid(security.WinLocalSystemSid, None),
        ):
            acl.AddAccessAllowedAceEx(
                security.ACL_REVISION, flags, ntsecuritycon.FILE_ALL_ACCESS, principal
            )
        security.SetNamedSecurityInfo(
            str(path),
            security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION
            | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
    else:
        if path.stat().st_uid != os.getuid():
            raise PermissionError("Private path must belong to this user")
        path.chmod(0o700 if directory else 0o600)


def assert_private_descriptor(descriptor):
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        raise PermissionError("Private data must be a regular file")
    if WINDOWS:
        import msvcrt

        security, _ = windows_security()
        assert_windows_descriptor(
            security.GetSecurityInfo(
                msvcrt.get_osfhandle(descriptor),
                security.SE_FILE_OBJECT,
                security.OWNER_SECURITY_INFORMATION
                | security.DACL_SECURITY_INFORMATION,
            )
        )
    elif info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("Private file must be owner-only (0600)")


@contextmanager
def private_reader(path):
    reject_link(path)
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    )
    try:
        assert_private_descriptor(descriptor)
        with os.fdopen(descriptor, encoding="utf-8-sig") as stream:
            descriptor = None
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)
