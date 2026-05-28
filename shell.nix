with import <nixpkgs> {};

mkShell {
  packages = [
    cmake
    llvmPackages_latest.clang
    llvmPackages_latest.lld
    llvmPackages_latest.llvm
    sqlite
    capnproto
    boost
    pkg-config
    libevent
    python3
    lcov
  ];

  shellHook = ''
    export CC=clang
    export CXX=clang++
  '';
}

