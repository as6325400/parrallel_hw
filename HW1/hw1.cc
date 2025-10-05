#include <cstdio>
#include <cstdlib>
#include <mpi.h>
#include <iostream>
#include <algorithm>
#include <boost/sort/spreadsort/spreadsort.hpp>

int mxlen;
float *tmp;
float *recvarr;
int *ranktable;
float *datas;

inline int merge_small(float* A, const float* B, int rk1, int rk2) {
    const int n = ranktable[rk1], m = ranktable[rk2];
    if (n == 0) return 0;
    int i = 0, j = 0, k = 0;
    while (k < n) {
        if (j >= m || (i < n && A[i] <= B[j])) tmp[k++] = A[i++];
        else                                   tmp[k++] = B[j++];
    }
    for (int t = 0; t < n; ++t) A[t] = tmp[t];
    return 1;
}


inline int merge_large(float* A, const float* B, int rk1, int rk2) {
    const int n = ranktable[rk1], m = ranktable[rk2];
    if (n == 0) return 0;
    int i = n - 1, j = m - 1, k = 0;
    while (k < n) {
        if (j < 0 || (i >= 0 && A[i] >= B[j]))  tmp[k++] = A[i--];
        else                                     tmp[k++] = B[j--];
    }
    int changed = 0;
    for (int t = 0; t < n; ++t) {
        float v = tmp[n - 1 - t];
        if (A[t] != v) { A[t] = v; changed = 1; }
    }
    return changed;
}


int merge_and_update(float *myarr, bool even, int rank, int size, MPI_Comm comm){
    int mylen = ranktable[rank], otrlen = 0;
    int neighbor = 0;
    if(even) {
        if(rank % 2 == 0) neighbor = rank + 1;
        else neighbor = rank - 1;
    } else {
        if(rank % 2 == 0) neighbor = rank - 1;
        else neighbor = rank + 1;
    }
    if(neighbor >= size || neighbor < 0) return 0;
    otrlen = ranktable[neighbor];
    if(mylen == 0 || otrlen == 0) return 0;

    float edge_me, edge_nb;

    if (rank < neighbor) {
        edge_me = myarr[mylen-1];
        MPI_Sendrecv(&edge_me, 1, MPI_FLOAT, neighbor, 201,
                     &edge_nb, 1, MPI_FLOAT, neighbor, 201,
                     comm, MPI_STATUS_IGNORE);
        if (edge_me <= edge_nb) return 0;
    } else {
        edge_me = myarr[0];
        MPI_Sendrecv(&edge_me, 1, MPI_FLOAT, neighbor, 201,
                     &edge_nb, 1, MPI_FLOAT, neighbor, 201,
                     comm, MPI_STATUS_IGNORE);
        if (edge_me >= edge_nb) return 0;
    }

    MPI_Sendrecv(myarr, mylen,  MPI_FLOAT, neighbor, 101,
                 recvarr, otrlen, MPI_FLOAT, neighbor, 101,
                 comm, MPI_STATUS_IGNORE);
    return (neighbor > rank)
         ? merge_small(myarr, recvarr, rank, neighbor)
         : merge_large(myarr, recvarr, rank, neighbor);
}

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);

    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    int N = atoi(argv[1]);
    const char *const input_filename = argv[2],
               *const output_filename = argv[3];
    
    MPI_File input_file, output_file;


    int tpl = N / size;
    int len = tpl, S;
    if(rank < N % size){
        len++;
        S = rank * len;
    } else{
        S = (tpl + 1) * (N % size) + (rank - (N % size)) * tpl;
    }

    mxlen = tpl + 1;
    ranktable = new int[size];
    for(int i = 0; i < size; i++){
        ranktable[i] = tpl;
        if(i < N % size) ranktable[i]++;
    }
    tmp = new float[mxlen];
    recvarr = new float[mxlen];
    datas = (len ? new float[len] : nullptr);

    MPI_File_open(MPI_COMM_WORLD, input_filename, MPI_MODE_RDONLY, MPI_INFO_NULL, &input_file);
    MPI_File_read_at(input_file, sizeof(float) * S, datas, len, MPI_FLOAT, MPI_STATUS_IGNORE);
    MPI_File_close(&input_file);

    boost::sort::spreadsort::spreadsort(datas, datas + len);

    int times = 1, k = 5;

    while(true){
        int local_odd = merge_and_update(datas, false, rank, size, MPI_COMM_WORLD);
        int local_even = merge_and_update(datas, true, rank, size, MPI_COMM_WORLD);
        int local_flag = local_odd | local_even, any_flag = 0;
        if(times > size){
            MPI_Allreduce(&local_flag,  &any_flag,  1, MPI_INT, MPI_LOR, MPI_COMM_WORLD);
            if (any_flag == 0) break;
        }
        times++;
    }

    MPI_File_open(MPI_COMM_WORLD, output_filename, MPI_MODE_CREATE|MPI_MODE_WRONLY, MPI_INFO_NULL, &output_file);
    MPI_File_write_at(output_file, sizeof(float) * S, datas, len, MPI_FLOAT, MPI_STATUS_IGNORE);
    MPI_File_close(&output_file);

    MPI_Finalize();

    return 0;
}
