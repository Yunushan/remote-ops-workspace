/* Make disposable multi-identity fixtures, including intentionally crossed keys. */
#include <stdio.h>
#include <stdlib.h>
#include <openssl/pem.h>
#include <openssl/pkcs12.h>

static void require(int ok)
{
    if (!ok) {
        fputs("could not construct disposable PKCS#12 fixture\n", stderr);
        exit(1);
    }
}

int main(int argc, char **argv)
{
    require(argc >= 5 && (argc - 3) % 2 == 0);
    const char *password = argv[2];
    STACK_OF(PKCS12_SAFEBAG) *bags = NULL;
    for (int index = 3; index < argc; index += 2) {
        FILE *certificate_file = fopen(argv[index], "rb");
        FILE *key_file = fopen(argv[index + 1], "rb");
        require(certificate_file && key_file);
        X509 *certificate = PEM_read_X509(certificate_file, NULL, NULL, NULL);
        EVP_PKEY *key = PEM_read_PrivateKey(key_file, NULL, NULL, NULL);
        fclose(certificate_file);
        fclose(key_file);
        require(certificate && key);
        unsigned char id[EVP_MAX_MD_SIZE];
        unsigned int id_length;
        require(X509_digest(certificate, EVP_sha256(), id, &id_length) == 1);
        PKCS12_SAFEBAG *certificate_bag = PKCS12_add_cert(&bags, certificate);
        PKCS12_SAFEBAG *key_bag = PKCS12_add_key(&bags, key, 0, 2048, NID_aes_256_cbc, password);
        require(certificate_bag && key_bag
                && PKCS12_add_localkeyid(certificate_bag, id, id_length)
                && PKCS12_add_localkeyid(key_bag, id, id_length));
        X509_free(certificate);
        EVP_PKEY_free(key);
    }
    STACK_OF(PKCS7) *safes = NULL;
    require(PKCS12_add_safe(&safes, bags, -1, 0, NULL));
    PKCS12 *bundle = PKCS12_add_safes(safes, NID_pkcs7_data);
    require(bundle && PKCS12_set_mac(bundle, password, -1, NULL, 0, 2048, EVP_sha256()));
    FILE *output = fopen(argv[1], "wb");
    require(output && i2d_PKCS12_fp(output, bundle));
    require(fclose(output) == 0);
    PKCS12_free(bundle);
    sk_PKCS7_pop_free(safes, PKCS7_free);
    sk_PKCS12_SAFEBAG_pop_free(bags, PKCS12_SAFEBAG_free);
    return 0;
}
