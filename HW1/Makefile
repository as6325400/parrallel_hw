CC = mpicc
CXX = mpicxx
CXXFLAGS = -std=c++17 -O3 -march=native -flto \
           -fno-math-errno -fno-trapping-math \
           -fopenmp -fopenmp-simd -DNDEBUG -funroll-loops -ftree-vectorize -g
CFLAGS   = -O3 -march=native -flto
TARGETS = hw1

.PHONY: all
all: $(TARGETS)

hw1: hw1.cc
	$(CXX) $(CXXFLAGS) -o $@ $<


.PHONY: clean
clean:
	rm -f $(TARGETS)

