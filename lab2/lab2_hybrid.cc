#include <assert.h>
#include <stdio.h>
#include <math.h>
#include <omp.h>
#include <mpi.h>

const int MX = 1000;

unsigned long long results[MX];

void calculate(int rank, int size, unsigned long long r, unsigned long long k){

	const long double rr = r * r;
	
	unsigned long long x0, x1;

	if (size == 1) {
    x0 = 0;
    x1 = r;
	} else {
    long double A = 1.5L;
		long double scale = A * (size - 1);

		unsigned long long k0 = rank;
		unsigned long long k1 = rank + 1;

		long double prefW0 = k0 * scale - (long double)(k0 * (k0 - 1)) / 2.0;
		long double prefW1 = k1 * scale - (long double)(k1 * (k1 - 1)) / 2.0;

		unsigned long long totalW = (unsigned long long)( (long double)size * scale - ((long double)size * (size - 1)) / 2.0 );

		x0 = (unsigned long long)((r * prefW0) / totalW);
		x1 = (unsigned long long)((r * prefW1) / totalW);
	}

	unsigned long long y0 = ceil(sqrtl(rr - (x0 * x0)));
	unsigned long long yy = rr - (x0 * x0);
	unsigned long long local_pixel = y0;

	if(x0 >= x1) local_pixel = 0;

	for (unsigned long long x = x0 + 1; x < x1; x ++)
	{	
		yy -= (2 * x - 1);
		unsigned long long y2 = y0 * y0;
		while (y0 && (y2 - (2*y0 - 1)) >= yy) {
				y2 -= (2*y0 - 1);
				--y0;
		}
		local_pixel += y0;
		if(local_pixel > k) local_pixel -= k;
	}
	results[rank] = local_pixel;
}

int main(int argc, char** argv)
{	
	if (argc != 3) {
		fprintf(stderr, "must provide exactly 2 arguments!\n");
		return 1;
	}

	MPI_Init(&argc, &argv);
	
	int mpi_rank, mpi_size;
	MPI_Comm_rank(MPI_COMM_WORLD, &mpi_rank);
	MPI_Comm_size(MPI_COMM_WORLD, &mpi_size);

	int cores = atoi(getenv("SLURM_CPUS_PER_TASK"));
	unsigned long long r = atoll(argv[1]), k = atoll(argv[2]);
	
	int total_workers = mpi_size * cores;

#pragma omp parallel num_threads(cores)
	{
		int omp_rank = omp_get_thread_num();
		int global_rank = mpi_rank * cores + omp_rank;
		calculate(global_rank, total_workers, r, k);
	}

	unsigned long long local_sum = 0;
	for(int i = 0; i < cores * mpi_size; i++){
		local_sum += results[i];
		local_sum %= k;
	}

	unsigned long long global_sum = 0;
	MPI_Reduce(&local_sum, &global_sum, 1, MPI_UNSIGNED_LONG_LONG, MPI_SUM, 0, MPI_COMM_WORLD);

	if(mpi_rank == 0) {
		printf("%llu\n", (global_sum * 4) % k);
	}

	MPI_Finalize();
	return 0;
}