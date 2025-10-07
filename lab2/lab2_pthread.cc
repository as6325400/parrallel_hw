#include <assert.h>
#include <stdio.h>
#include <math.h>
#include <pthread.h>
#include <thread>

typedef struct{
	int rank, size;
	unsigned long long r, k;
}metaDeta;

const int MX = 10;

metaDeta datas[MX];
pthread_t th[MX];
unsigned long long results[MX];

void *calculate(void* arg){
	metaDeta* data = (metaDeta*)arg;

	int rank = data -> rank;
	int size = data -> size;
	unsigned long long r = data -> r;
	unsigned long long k = data -> k;

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
		while (y0 && (y2 - (2*y0 - 1)) >= yy) { // (y0-1)^2 = y2 - (2y0-1)
				y2 -= (2*y0 - 1);
				--y0;
		}
		local_pixel += y0;
		if(local_pixel > k) local_pixel -= k;
	}
	results[rank] = local_pixel;
	return NULL;
}

int main(int argc, char** argv)
{	
	if (argc != 3) {
		fprintf(stderr, "must provide exactly 2 arguments!\n");
		return 1;
	}

	int cores = atoi(getenv("SLURM_CPUS_PER_TASK"));
	unsigned long long r = atoll(argv[1]), k = atoll(argv[2]), pixels = 0;

	for(int i = 0; i < cores; i++){
		datas[i].rank = i;
		datas[i].size = cores;
		datas[i].r = r;
		datas[i].k = k;
		pthread_create(&th[i], NULL, calculate, &datas[i]);
	}

	for(int i = 0; i < cores; i++){
		pthread_join(th[i], NULL);
	}

	unsigned long long sum = 0;

	for(int i = 0; i < cores; i++){
		sum += results[i];
		sum %= k;
	}

	printf("%llu\n", (sum * 4) % k);

	return 0;
}

