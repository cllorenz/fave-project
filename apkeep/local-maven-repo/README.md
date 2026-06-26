# Vendored Maven repository — JDD

This is an in-tree, file-based Maven repository holding the **JDD** dependency
that APKeep needs, vendored so the APKeep build is hermetic (no network, no
JitPack).

## Why this exists (FaVe fork)

APKeep's `pom.xml` declares `org.bitbucket.vahidi:JDD:108`, but:

- JDD is **not on Maven Central**.
- The pinned tag `108` was **never published** on the upstream JDD repo (its
  tags start at `109`).
- JitPack (which maps Bitbucket repos to `org.bitbucket.<user>`) serves only
  JDD's `.pom`, **never a `.jar`** — JDD is a Gradle/Ant project that produces
  no JitPack-resolvable Maven artifact.

So upstream `mvn package` cannot resolve JDD at all. We vendor a jar here and
point `apkeep/pom.xml` at this repository (`fave-vendored-jdd`).

## Artifact provenance

- **Coordinate:** `org.bitbucket.vahidi:JDD:111`
- **Source:** <https://bitbucket.org/vahidi/jdd> at tag `111` (Arash Vahidi, 2019).
- **Build:** compiled from `src/` with `javac` (JDK 11) and packaged with `jar`
  — Gradle was bypassed because its build script applies the now-defunct
  `com.jfrog.bintray` plugin (jcenter is gone), which fails at configuration
  time. JDD has no runtime dependencies (junit is test-scope only), so a plain
  `javac src/**.java` + `jar` reproduces the library.
- **Version note:** upstream pinned `108`; `111` is the nearest existing tag
  from the same author. The BDD API APKeep uses
  (`and`/`not`/`ref`/`deref`/`exists`/`or`/`diff`) is long-stable across it.

## License

JDD is released under a **zlib-style / public-domain** license (Copyright ©
2002–2019 Arash Vahidi) — redistribution, including of compiled binaries, is
permitted. See the JDD `LICENSE` at the source repo above.
