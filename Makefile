.PHONY: clean build shell test cov

NUM_JOBS=1

# To run:
# nix-shell --pure --run 'make clean build && exec $SHELL'

shell:
	nix-shell --pure

# https://github.com/bitcoin/bitcoin/blob/master/doc/developer-notes.md#using-llvmclang-toolchain
build:
	cmake -B build -DCMAKE_C_COMPILER="clang" \
	-DCMAKE_CXX_COMPILER="clang++" \
	-DAPPEND_CFLAGS="-fprofile-instr-generate -fcoverage-mapping" \
	-DAPPEND_CXXFLAGS="-fprofile-instr-generate -fcoverage-mapping" \
	-DAPPEND_LDFLAGS="-fprofile-instr-generate -fcoverage-mapping"
	cmake --build build -j ${NUM_JOBS}

test:
	mkdir -p build/raw_profile_data
	LLVM_PROFILE_FILE="${CURDIR}/build/raw_profile_data/%m_%p.profraw" ctest --test-dir build -j ${NUM_JOBS}
	LLVM_PROFILE_FILE="${CURDIR}/build/raw_profile_data/%m_%p.profraw" build/test/functional/test_runner.py -j ${NUM_JOBS}
	find build/raw_profile_data -name "*.profraw" > build/raw_profile_data_files.txt
	llvm-profdata merge -f build/raw_profile_data_files.txt -o build/coverage.profdata

cov:
	llvm-cov show \
	    --object=build/bin/test_bitcoin \
	    --object=build/bin/bitcoind \
	    -Xdemangler=llvm-cxxfilt \
	    --instr-profile=build/coverage.profdata \
	    --ignore-filename-regex="src/crc32c/|src/leveldb/|src/minisketch/|src/secp256k1/|src/test/" \
	    --format=html \
	    --show-instantiation-summary \
	    --show-line-counts-or-regions \
	    --show-expansions \
	    --output-dir=build/coverage_report \
	    --project-title="Bitcoin Core Coverage Report"

clean:
	rm -rf build
