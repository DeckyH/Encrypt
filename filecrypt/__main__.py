"""Command line front end. Run as: python3 -m filecrypt ..."""

import argparse
import getpass
import os
import sys

from . import __version__, core, legacy


# ---------------------------------------------------------------- selection

def gather(paths, suffix_filter, recursive, include_hidden):
    """Expand paths into a list of regular files.

    Directories are skipped rather than handed to open() -- the 2021 code
    crashed with IsADirectoryError partway through a run and left the rest
    of the folder untouched.

    suffix_filter(name) decides whether a file is in scope. Matching is on
    the suffix, never on a substring: 'reference.txt' contains "enc" and
    the old code silently refused to encrypt it.
    """
    out, skipped = [], []
    for p in paths:
        if os.path.isfile(p):
            out.append(p)
            continue
        if not os.path.isdir(p):
            skipped.append((p, "no such file or directory"))
            continue
        walker = os.walk(p) if recursive else [(p, [], _files_in(p))]
        for root, _dirs, names in walker:
            for n in sorted(names):
                full = os.path.join(root, n)
                if not os.path.isfile(full):
                    continue
                if n.startswith(".") and not include_hidden:
                    skipped.append((full, "hidden file (use --include-hidden)"))
                    continue
                if not suffix_filter(n):
                    skipped.append((full, "not in scope for this action"))
                    continue
                out.append(full)
    return out, skipped


def _files_in(d):
    return [n for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))]


# ------------------------------------------------------------------ prompts

def ask_secrets(confirm, label="", pw=None, salt=None):
    """Prompt for password and salt.

    Both are confirmed when encrypting. Neither format authenticates the
    salt against anything stored, so a typo at encrypt time is permanent
    and silent -- the second prompt is the only thing standing between the
    user and an unopenable archive.
    """
    tag = f" ({label})" if label else ""
    pw = pw or getpass.getpass(f"Password{tag}: ")
    if confirm and pw != getpass.getpass(f"Confirm password{tag}: "):
        raise SystemExit("passwords do not match")
    salt = salt or getpass.getpass(f"Salt{tag}: ")
    if confirm and salt != getpass.getpass(f"Confirm salt{tag}: "):
        raise SystemExit("salts do not match")
    if not pw or not salt:
        raise SystemExit("password and salt are both required")
    return pw, salt


def report(done, failed, skipped, verbose):
    for path, why in failed:
        print(f"  FAILED  {path}: {why}", file=sys.stderr)
    if verbose:
        for path, why in skipped:
            print(f"  skipped {path}: {why}")
    print(f"\n{len(done)} processed, {len(failed)} failed, {len(skipped)} skipped")
    if skipped and not verbose:
        print("re-run with -v to see what was skipped")
    return 1 if failed else 0


# ----------------------------------------------------------------- commands

def cmd_encrypt(args):
    pw, salt = ask_secrets(confirm=True)
    targets, skipped = gather(args.paths, lambda n: not n.endswith(core.SUFFIX),
                              args.recursive, args.include_hidden)
    done, failed = [], []
    for src in targets:
        dst = src + core.SUFFIX
        if os.path.exists(dst) and not args.force:
            failed.append((src, f"{os.path.basename(dst)} exists (use --force)"))
            continue
        try:
            core.encrypt_file(src, dst, pw, salt, iterations=args.iterations)
            print(f"  encrypted {src}")
            done.append(src)
            if args.remove_originals:
                os.remove(src)
        except (core.CryptError, OSError) as e:
            failed.append((src, str(e)))
    if done and not args.remove_originals:
        print("\nnote: originals were left in place and are still readable")
    return report(done, failed, skipped, args.verbose)


def cmd_decrypt(args):
    pw, salt = ask_secrets(confirm=False)
    targets, skipped = gather(args.paths, lambda n: n.endswith(core.SUFFIX),
                              args.recursive, args.include_hidden)
    done, failed = [], []
    for src in targets:
        dst = src[: -len(core.SUFFIX)]
        if os.path.abspath(dst) == os.path.abspath(src):
            failed.append((src, "output would overwrite the input"))
            continue
        if os.path.exists(dst) and not args.force:
            failed.append((src, f"{os.path.basename(dst)} exists (use --force)"))
            continue
        try:
            core.decrypt_file(src, dst, pw, salt)
            print(f"  decrypted {src}")
            done.append(src)
        except (core.CryptError, OSError) as e:
            failed.append((src, str(e)))
    return report(done, failed, skipped, args.verbose)


def cmd_migrate(args):
    """Read 2021 .enc files and rewrite them in the authenticated format."""
    old_pw, old_salt = ask_secrets(confirm=False, label="old .enc files")
    if args.reuse_credentials:
        new_pw, new_salt = old_pw, old_salt
    else:
        new_pw, new_salt = ask_secrets(confirm=True, label="new .fc2 files")

    targets, skipped = gather(args.paths, lambda n: n.endswith(legacy.SUFFIX),
                              args.recursive, args.include_hidden)
    done, failed, flagged = [], [], []
    for src in targets:
        dst = legacy.output_name(src) + core.SUFFIX
        if os.path.exists(dst) and not args.force:
            failed.append((src, f"{os.path.basename(dst)} exists (use --force)"))
            continue
        try:
            raw, info = legacy.decrypt_file(src, old_pw, old_salt)
            plaintext = info["historical"]
            if info["guaranteed_lost"]:
                flagged.append((src, info))
                if args.keep_padded:
                    plaintext = raw
            with open(dst, "wb") as fh:
                fh.write(core.encrypt_bytes(plaintext, new_pw, new_salt,
                                            iterations=args.iterations))
            print(f"  migrated {src}")
            done.append(src)
        except (legacy.LegacyError, core.CryptError, OSError) as e:
            failed.append((src, str(e)))

    if flagged:
        print("\nthese files ended in null bytes -- the 2021 decrypter would "
              "have truncated them:")
        for src, info in flagged:
            print(f"  {src}: at least {info['guaranteed_lost']} byte(s) of real "
                  f"data, original length between {info['min_len']} and "
                  f"{info['max_len']}")
        print("the null padding is ambiguous, so the exact original length "
              "cannot be recovered from the ciphertext alone.")
        if not args.keep_padded:
            print("re-run with --keep-padded to preserve every byte, including "
                  "up to 16 bytes of padding.")
    print("\nnothing was deleted; verify the new files before removing the old ones")
    return report(done, failed, skipped, args.verbose)


def cmd_gui(args):
    from . import gui
    return gui.main()


# -------------------------------------------------------------------- parser

def build_parser():
    p = argparse.ArgumentParser(
        prog="filecrypt",
        description="Authenticated file encryption (AES-256-GCM).")
    p.add_argument("--version", action="version", version=f"filecrypt {__version__}")
    subs = p.add_subparsers(dest="command", required=True)

    def shared(sp, hidden=True):
        sp.add_argument("paths", nargs="+", help="files or directories")
        sp.add_argument("-r", "--recursive", action="store_true",
                        help="descend into subdirectories")
        sp.add_argument("--include-hidden", action="store_true",
                        help="include dotfiles such as .DS_Store")
        sp.add_argument("-f", "--force", action="store_true",
                        help="overwrite existing output files")
        sp.add_argument("-v", "--verbose", action="store_true",
                        help="list skipped files and why")
        return sp

    e = shared(subs.add_parser("encrypt", help="encrypt files"))
    e.add_argument("--iterations", type=int, default=core.DEFAULT_ITERATIONS,
                   help=f"PBKDF2 iterations (default {core.DEFAULT_ITERATIONS})")
    e.add_argument("--remove-originals", action="store_true",
                   help="delete each plaintext after it is encrypted")
    e.set_defaults(func=cmd_encrypt)

    d = shared(subs.add_parser("decrypt", help="decrypt files"))
    d.set_defaults(func=cmd_decrypt)

    m = shared(subs.add_parser("migrate", help="convert 2021 .enc files to .fc2"))
    m.add_argument("--iterations", type=int, default=core.DEFAULT_ITERATIONS)
    m.add_argument("--reuse-credentials", action="store_true",
                   help="use the old password and salt for the new files too")
    m.add_argument("--keep-padded", action="store_true",
                   help="keep trailing null padding where the original length "
                        "is ambiguous")
    m.set_defaults(func=cmd_migrate)

    g = subs.add_parser("gui", help="launch the graphical interface")
    g.set_defaults(func=cmd_gui)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
