from storages.backends.s3 import S3Storage


class PrivateS3Storage(S3Storage):
    def url(self, name, *args, **kwargs):
        raise NotImplementedError('Use o download autenticado do HelpDesk.')
