Is there such fs that stores data by it hashes and guarantees such invariant? Can zfs do this? Is there some projects like this?

---------------------

Yes. What you’re describing is usually called **content-addressed storage (CAS)**: the identity/location of a block or object is derived from a cryptographic hash of its contents, e.g.

`id = BLAKE3(data)`

and the core invariant is essentially:

`store[H(data)] == data`

If you additionally require that two identical blocks *must* resolve to the same physical storage object, that gives you intrinsic deduplication.

ZFS is close, but it is **not fundamentally a content-addressed filesystem**. ZFS computes checksums for every block and stores the checksum in the parent block pointer, giving it a Merkle-tree-like integrity structure. citeturn856865search33turn856865search7 But a ZFS block's checksum is normally an integrity property, not its address. The block pointer still contains physical locations/DVAs.

With ZFS dedup enabled, things get considerably closer. ZFS maintains a Deduplication Table mapping block checksums to existing physical blocks; when a newly written block has the same checksum, it can reference the existing block instead. With `dedup=verify`, ZFS also performs a byte-for-byte comparison before treating two checksum-equal blocks as identical, so even an actual hash collision doesn't violate correctness. citeturn856865search3 Recent OpenZFS also supports BLAKE3 for checksumming/dedup. citeturn856865search1

So conceptually:

```text
Pure CAS:
hash(data) ───────► data

ZFS:
logical block
│
▼
block pointer ───► physical block
│
└── checksum(data)

ZFS + dedup:
checksum(data) ──► DDT ──► physical block
```

The distinction matters. In CAS, the hash is part of the **namespace/addressing model**. In ZFS, the hash is primarily an integrity identifier and optionally a dedup key. You can't normally say "give me ZFS block `b3:abc123…`" as the filesystem's native access model.

There are several systems/projects much closer to what you're imagining:

- **IPFS / UnixFS** is explicitly content-addressed. Files are chunked into blocks, each block has a CID derived from its content, and directories/files form a Merkle DAG. A root CID commits transitively to an entire tree. citeturn856865search4turn856865search0
- **Git** is perhaps the cleanest familiar example. Objects are addressed by hash; trees contain hashes of child objects. It is effectively a persistent immutable Merkle DAG, although it isn't intended as a general POSIX filesystem.
- **casync** splits files/images into content-defined chunks and stores each chunk under its cryptographic hash. It's particularly interesting for backups/images/versioned trees. citeturn856865search6
- **Nix/Guix** use content-addressing heavily at the package/store level, although their exact path hashing semantics include derivation/build inputs rather than simply being `hash(file bytes)`.
- **IPLD / various CAS object stores** give you the building blocks for an actual hash-addressed filesystem.

There are also smaller local CAS projects that put blobs into a vault named by BLAKE3 hashes and expose/ref-link them into a conventional filesystem; for example `bdstorage` does exactly that and can use ZFS 2.2+ block cloning underneath. citeturn856865search2

There is one subtlety in your word **"guarantees."** If the invariant is literally:

```text
H(x) == H(y) => x == y
```

no fixed-length cryptographic hash can mathematically guarantee that. Pigeonhole principle says collisions necessarily exist. You can only make them astronomically improbable.

There are two ways around that:

```text
1. Practical cryptographic invariant:
BLAKE3/SHA-256 equality is treated as equality.
Collision probability ≈ irrelevant in practice.

2. Strict invariant:
use hash as lookup key,
but on collision compare complete contents.
```

ZFS `dedup=verify` takes approach 2, which is pretty nice: the hash gets you the candidate block, but byte comparison preserves correctness even if the hash collides. citeturn856865search3

If your goal is something stronger like **"the entire physical filesystem should be a canonical Merkle DAG, with no mutable block identities at all"**, ZFS doesn't quite implement that model. IPFS/IPLD, Git-style object stores, CASync, or building a thin filesystem on top of a CAS are much closer.

For your sort of storage setup, an especially interesting architecture would be **CAS objects stored on ZFS**: BLAKE3 content-defined chunks → immutable CAS objects → Merkle trees for files/directories → ZFS underneath for checksumming, RAIDZ/mirrors, snapshots and scrubbing. That gives you two independent layers of integrity rather than trying to force ZFS itself into being CAS.

---------------------

I would like to address them as hash

Do zfs can do that?

---------------------

Not natively, no.

ZFS does **not** expose blocks/files through a public API like:

```text
read(hash) -> contents
```

Its checksums are stored in block pointers for integrity, and with deduplication the checksum is also used internally as a key in the DDT. But that DDT is an implementation detail; ZFS still addresses live data through normal filesystem objects, block pointers, and physical DVAs.

So even with:

```text
dedup=on
checksum=blake3
```

you cannot normally do something equivalent to:

```bash
zfs-cat blake3:012345...
```

and retrieve the block identified by that digest.

You could build this **on top of ZFS**, though, very naturally:

```text
/objects/b3/ab/cd/abcdef...
```

where each file is immutable and its pathname is its BLAKE3 digest:

```text
put(data):
h = BLAKE3(data)
write /objects/b3/<h>
return h

get(h):
return read /objects/b3/<h>
```

ZFS underneath then gives you checksumming, scrubbing, redundancy, snapshots, compression, and optionally block cloning/deduplication.

If you want the hash to be the *actual storage address*, rather than merely a filename convention, you want a genuine CAS such as Git's object database, IPFS/IPLD, or a purpose-built CAS layer. ZFS is an excellent backing store for one, but ZFS itself isn't one.

---------------------

What about ipfs/unixfs? And nix store

---------------------

**IPFS/UnixFS is much closer to exactly what you want than ZFS. Nix is only partially so.**

With **IPFS**, content is genuinely addressed by a CID. Conceptually:

```text
CID = metadata(hash(data))
get(CID) -> data
```

For an individual raw IPFS block, the CID contains the cryptographic digest of that block, plus information such as hash algorithm and codec. You can directly retrieve by CID. citeturn384737search2

UnixFS then builds files and directories on top of those content-addressed blocks:

```text
file CID
|
+--> CID(chunk 1)
+--> CID(chunk 2)
+--> CID(chunk 3)
```

Directories work similarly:

```text
directory CID
|
+-- "foo" --> CID(foo)
+-- "bar" --> CID(bar)
```

So the root CID commits to the entire tree underneath it. That's basically the Merkle-DAG filesystem model you're describing. citeturn384737search0turn384737search1

One caveat: a UnixFS **file CID isn't necessarily `hash(file bytes)`**. Large files are chunked, and the root CID hashes the DAG representation. Chunk size, chunking algorithm, tree layout, codec, CID version, etc. can affect the final CID. Thus identical file bytes can have different UnixFS CIDs if imported using different parameters. citeturn384737search2

For a raw single-block object, however, it's essentially exactly:

```text
SHA256(bytes) -> CID -> bytes
```

### Nix store

Nix looks similar superficially:

```text
/nix/store/5skmmcb9svys5lj3kbsrjg7vf2irid63-hello-2.10
```

but historically **most Nix store paths are not hashes of their contents**.

Traditional Nix is *input-addressed*: the path derives primarily from the derivation/build inputs. This is why two builds with the same derivation are expected to land at the same path, even before the output bytes are known. citeturn429486search5

Modern Nix does support actual **content-addressed store objects**. For those, the store-path digest is computed from properties intrinsic to the resulting object: its filesystem object graph, references, store directory and name. citeturn429486search0

So you can get:

```text
content
|
v
content address
|
v
/nix/store/<digest>-name
```

and Nix can verify such an object without trusting a signature from the binary cache. citeturn429486search5

But even content-addressed Nix isn't as clean as:

```text
BLAKE3(bytes) -> bytes
```

because the Nix store path digest isn't simply the raw object's hash. Store objects can contain references to other store objects, filesystem trees need canonical serialization/hashing, and the store directory/name participate in the store-address computation. citeturn429486search0turn429486search1

So I'd characterize them this way:

| System | Hash is native address? | Can fetch directly by content address? | Hierarchical filesystem |
|---|---|---|---|
| ZFS | No | No | Yes |
| IPFS blocks | **Yes** | **Yes** | No |
| UnixFS | **Yes, via Merkle DAG CID** | **Yes** | **Yes-ish** |
| Git objects | **Yes** | **Yes** | Trees, not POSIX FS |
| Nix traditional store | No, input-addressed | By store path | Store objects |
| Nix CA store | **Mostly yes** | By content-derived store path | Store objects |

If your desired primitive is literally:

```text
put(bytes) -> hash
get(hash) -> bytes
```

**IPFS blockstore/IPLD is the cleaner model.**

If your desired primitive is:

```text
put(directory tree) -> hash
get(hash) -> immutable directory tree
```

**UnixFS/IPLD is almost exactly it.**

And importantly, you don't need the IPFS P2P network to use this idea. You can use the **content-addressed blockstore + IPLD/UnixFS locally**, with ZFS underneath as the durable storage layer. That combination is probably closer to what you're imagining than either ZFS or Nix alone.