.PHONY: clean build shell test cov

NUM_JOBS=1

# To run:
# nix-shell --pure --run 'make clean build && exec $SHELL'

shell:
	nix-shell --pure

# https://github.com/bitcoin/bitcoin/blob/master/doc/developer-notes.md#using-lcov
build:
	cmake -B build \
		-DCMAKE_BUILD_TYPE=Coverage \
		-DCMAKE_C_COMPILER=gcc \
		-DCMAKE_CXX_COMPILER=g++
	cmake --build build -j ${NUM_JOBS}

test:
	cmake -DJOBS="${NUM_JOBS}" -P build/Coverage.cmake
	@printf '%s\n' "Coverage report: build/total.coverage/index.html"

clean:
	rm -rf build
