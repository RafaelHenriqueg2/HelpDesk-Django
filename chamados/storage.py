from storages.backends.s3 import S3Storage


class ArmazenamentoPrivadoS3(S3Storage):
    """Impede links públicos; os downloads devem passar pelas permissões do portal."""
    def url(self, name, *args, **kwargs):
        raise NotImplementedError('Use o download autenticado do HelpDesk.')
