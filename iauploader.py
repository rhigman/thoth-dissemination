#!/usr/bin/env python3
"""
Retrieve and disseminate files and metadata to Internet Archive
"""

import logging
import sys
from internetarchive import upload
from io import BytesIO
from os import environ
from uploader import Uploader


class IAUploader(Uploader):
    """Dissemination logic for Internet Archive"""

    def upload_to_platform(self):
        """Upload work in required format to Internet Archive"""

        # Use Thoth ID as unique identifier (URL will be in format `archive.org/details/[identifier]`)
        filename = self.work_id

        metadata_bytes = self.get_formatted_metadata('json::thoth')
        pdf_bytes = self.get_pdf_bytes()

        # Convert Thoth work metadata into Internet Archive format
        ia_metadata = self.parse_metadata()

        responses = upload(
            identifier=filename,
            files={
                '{}.pdf'.format(filename): BytesIO(pdf_bytes),
                '{}.json'.format(filename): BytesIO(metadata_bytes),
            },
            metadata=ia_metadata,
            access_key=environ.get('ia_s3_access'),
            secret_key=environ.get('ia_s3_secret'),
        )

        for response in responses:
            if response.status_code != 200:
                logging.error(
                    'Error uploading to Internet Archive: {}'.format(response.text))
                sys.exit(1)

        logging.info(
            'Successfully uploaded to Internet Archive at archive.org/details/{}'.format(filename))

    def parse_metadata(self):
        """Convert work metadata into Internet Archive format"""
        work_metadata = self.metadata.get('data').get('work')
        # Repeatable fields such as 'creator', 'isbn', 'subject'
        # can be set by submitting a list of values
        creators = [n.get('fullName')
                    for n in work_metadata.get('contributions') if n.get('mainContribution') == True]
        # IA metadata schema suggests hyphens should be omitted,
        # although including them does not cause any errors
        isbns = [n.get('isbn').replace(
            '-', '') for n in work_metadata.get('publications') if n.get('isbn') is not None]
        # We may want to mark BIC, BISAC, Thema etc subject codes as such;
        # IA doesn't set a standard so representations vary across the archive
        subjects = [n.get('subjectCode')
                    for n in work_metadata.get('subjects')]
        languages = [n.get('languageCode')
                     for n in work_metadata.get('languages')]
        issns = [n.get('series').get(key) for n in work_metadata.get(
            'issues') for key in ['issnPrint', 'issnDigital']]
        # IA only accepts a single volume number
        volume = next(iter([str(n.get('issueOrdinal'))
                      for n in work_metadata.get('issues')]), None)
        ia_metadata = {
            # All fields are non-mandatory
            # Any None values or empty lists are ignored by IA on ingest
            'title': work_metadata.get('fullTitle'),
            'publisher': self.get_publisher_name(),
            'creator': creators,
            # IA requires date in YYYY-MM-DD format, as output by Thoth
            'date': work_metadata.get('publicationDate'),
            'description': work_metadata.get('longAbstract'),
            # Field name is misleading; displayed in IA as 'Pages'
            'imagecount': work_metadata.get('pageCount'),
            'isbn': isbns,
            'lccn': work_metadata.get('lccn'),
            'licenseurl': work_metadata.get('license'),
            'mediatype': 'texts',
            'oclc-id': work_metadata.get('oclc'),
            # IA has no dedicated DOI field but 'source' is
            # "[u]sed to signify where a piece of media originated"
            'source': work_metadata.get('doi'),
            # https://help.archive.org/help/uploading-a-basic-guide/ requests no more than
            # 10 subject tags, but additional tags appear to be accepted without error
            'subject': subjects,
            'language': languages,
            'issn': issns,
            'volume': volume,
            # Custom field helping future users determine what logic was used to create an upload
            'thoth-dissemination-service': self.version,
        }

        return ia_metadata
