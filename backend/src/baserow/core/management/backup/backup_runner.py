import math
import re

# See nosec comment later in file.
import subprocess  # nosec
import tarfile
import tempfile
from pathlib import Path
from typing import List, Optional

from django.utils import timezone

import psycopg2

from baserow.contrib.database.fields.models import LinkRowField, MultipleSelectField
from baserow.contrib.database.table.models import Table
from baserow.core.management.backup.exceptions import InvalidBaserowBackupArchive

NO_USER_TABLES_BACKUP_SUB_FOLDER = "everything_but_user_tables"


class BaserowBackupRunner:
    """
    A class which can backup or restore the database used by an installation of
    Baserow. Under the hood it uses `pg_dump` and `pg_restore` commands.
    """

    def __init__(
        self,
        host: str,
        database: str,
        username: str,
        port: Optional[str] = "5432",
        jobs: Optional[int] = 1,
    ):
        """
        Constructs a BaserowBackupRunner.

        :param host: The host name of the database.
        :param database: The name of the database to back-up.
        :param username: The username to connect to the database as.
        :param port: The port to connect to the database using.
        :param jobs: How many parallel dump/restart jobs to run per batch.
        """

        self.host = host
        self.database = database
        self.username = username
        self.port = port
        self.jobs = jobs

    def backup_baserow(
        self,
        backup_file_name: Optional[str] = None,
        batch_size: Optional[int] = 60,
        additional_pg_dump_args: Optional[List[str]] = None,
    ) -> str:
        """
        Backs up an entire Database containing an installation of Baserow.

        :param backup_file_name: The entire file path including the file name to store
            the backup file in. If not provided then the current working directory
            with a default file name is used.
        :param batch_size: How many tables to dump in each sub dump run by this command.
        :param additional_pg_dump_args: Additional command line arguments passed to
        each run of pg_dump.
        :return: Returns the file path/name of the created back-up file.
        :raises InvalidBaserowBackupArchive: When the provided backup archive does not
            meet the expected baserow backup format.
        :raises CalledProcessError: When one of the sub commands fails.
        """

        backup_file_name = backup_file_name or _default_backup_location(self.database)
        if additional_pg_dump_args is None:
            additional_pg_dump_args = []

        try:
            self._open_files_and_run_backup(
                backup_file_name, batch_size, additional_pg_dump_args
            )
            return backup_file_name
        except Exception as e:
            # An empty tar file will still be created if an exception occurs,
            # clean it up so the user isn't confused by invalid back-up files being
            # made.
            backup_file_to_cleanup = Path(backup_file_name)
            if backup_file_to_cleanup.is_file():
                backup_file_to_cleanup.unlink()
            raise e

    def restore_baserow(
        self,
        backup_file_name: str,
        additional_pg_restore_args: Optional[List[str]] = None,
    ):
        """
        Restores a database in it's entirety from a backup file generated by the
        `backup_baserow` function.

        :param backup_file_name: The full file path including the file name of the
            backup file to restore from.
        :param additional_pg_restore_args: Additional command line arguments passed to
            every run of pg_restore.
        :raises CalledProcessError: When one of the sub commands fails.
        """

        if additional_pg_restore_args is None:
            additional_pg_restore_args = []

        with tempfile.TemporaryDirectory() as temporary_directory_name:
            with tarfile.open(backup_file_name, "r:gz") as backup_input_tar:
                backup_input_tar.extractall(temporary_directory_name)

            backup_internal_folder_name = Path(backup_file_name).name
            backup_sub_folder = Path(
                temporary_directory_name, backup_internal_folder_name
            ).resolve()
            if not backup_sub_folder.is_dir():
                raise InvalidBaserowBackupArchive(
                    f"Expected to find a folder inside {backup_file_name} called "
                    f"{backup_internal_folder_name} but it wasn't there. Is the file "
                    "you provided a valid baserow backup file generated by ./baserow "
                    "backup_baserow ?"
                )

            self._restore_everything_but_user_tables(
                backup_sub_folder, additional_pg_restore_args
            )
            self._restore_user_tables_from_batch_back_ups(
                backup_sub_folder, additional_pg_restore_args
            )

    def _build_pg_dump_command(self, extra_command: List[str]) -> List[str]:
        return ["pg_dump"] + self._get_postgres_tool_args() + extra_command

    def _get_postgres_tool_args(self) -> List[str]:
        params = [
            "--host=" + self.host,
            "--dbname=" + self.database,
            "--port=" + self.port,
            "--username=" + self.username,
            # Run in directory mode so we can do parallel dumps using the jobs flag.
            "-Fd",
            "--jobs=" + str(self.jobs),
            # Force non-interactive password input as we will be running many
            # separate pg_dump commands and entering the password over and over is
            # horrible.
            "-w",
        ]
        return params

    def _build_pg_restore_command(self, extra_command: List[str]) -> List[str]:
        return ["pg_restore"] + self._get_postgres_tool_args() + extra_command

    def _build_connection(self):
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.username,
        )

    def _backup_everything_but_user_tables(
        self,
        temporary_directory_name: str,
        additional_pg_dump_args: List[str],
    ):
        args = [
            f"--exclude-table={MultipleSelectField.THROUGH_DATABASE_TABLE_PREFIX}*",
            f"--exclude-table={Table.USER_TABLE_DATABASE_NAME_PREFIX}*",
            f"--exclude-table={LinkRowField.THROUGH_DATABASE_TABLE_PREFIX}*",
            f"--file={temporary_directory_name}/everything_but_user_tables/",
        ]
        self._run_command_in_sub_process(
            self._build_pg_dump_command(args + additional_pg_dump_args),
        )

    def _backup_user_tables_in_batches(
        self,
        batch_size: int,
        output_directory: str,
        additional_pg_dump_args: List[str],
    ):
        """
        Loops over all the user tables in the provided database pg_dumps them in batches
        into sub-folders in the output_directory.

        :param batch_size: How many tables should be dumped in each batch.
        :param output_directory: The directory to write the resulting back up
            directories into.
        """

        with self._build_connection() as connection:
            sorted_user_table_names = _get_sorted_user_tables_names(connection)
        num_batches = math.ceil(len(sorted_user_table_names) / batch_size)
        for batch_num in range(num_batches):
            tables_to_dump_this_batch = sorted_user_table_names[
                batch_num * batch_size : (batch_num + 1) * batch_size
            ]
            pg_dump_tables_include_arg = [
                f"--table={t}" for t in tables_to_dump_this_batch
            ]
            self._run_command_in_sub_process(
                self._build_pg_dump_command(
                    pg_dump_tables_include_arg
                    + [f"--file={output_directory}/user_tables_batch_{batch_num}/"]
                    + additional_pg_dump_args
                ),
            )

    def _restore_everything_but_user_tables(
        self,
        extracted_backup_location: Path,
        additional_pg_restore_args: List[str],
    ):
        command = self._build_pg_restore_command(
            [
                f"{str(extracted_backup_location)}/{NO_USER_TABLES_BACKUP_SUB_FOLDER}/",
            ]
            + additional_pg_restore_args
        )
        self._run_command_in_sub_process(
            command,
        )

    def _restore_user_tables_from_batch_back_ups(
        self,
        extracted_backup_location: Path,
        additional_pg_restore_args: List[str],
    ):
        for child in extracted_backup_location.iterdir():
            if child.name != NO_USER_TABLES_BACKUP_SUB_FOLDER:
                self._run_command_in_sub_process(
                    self._build_pg_restore_command(
                        [
                            str(child),
                        ]
                        + additional_pg_restore_args
                    ),
                )

    def _open_files_and_run_backup(
        self,
        backup_file_name: str,
        batch_size: int,
        additional_pg_dump_args: List[str],
    ):
        with tarfile.open(backup_file_name, "w:gz") as backup_output_tar:
            with tempfile.TemporaryDirectory() as temporary_directory_name:
                self._backup_everything_but_user_tables(
                    temporary_directory_name, additional_pg_dump_args
                )
                self._backup_user_tables_in_batches(
                    batch_size, temporary_directory_name, additional_pg_dump_args
                )
                backup_internal_folder_name = Path(backup_file_name).name
                backup_output_tar.add(
                    temporary_directory_name, arcname=backup_internal_folder_name
                )

    # noinspection PyMethodMayBeStatic
    def _run_command_in_sub_process(self, command):
        print(" ".join(command))
        # Adding nosec ignore as this is only used by admin only command line tools
        # where it it is completely reasonable to use subprocess and not insecure.
        subprocess.check_output(command)  # nosec


def _get_sorted_user_tables_names(conn) -> List[str]:
    """
    Queries the provided connection for the table and schema names of Baserow's user
    tables. The returned list is sorted by schema, the type of table (relation vs
    actual table) and finally by the ID of the table numerically.
    """

    with conn.cursor() as cursor:

        table_prefix_regex_escaped = re.escape(Table.USER_TABLE_DATABASE_NAME_PREFIX)
        through_table_regex_escaped = re.escape(
            LinkRowField.THROUGH_DATABASE_TABLE_PREFIX
        )
        multipleselect_table_regex_escaped = re.escape(
            MultipleSelectField.THROUGH_DATABASE_TABLE_PREFIX
        )
        # Ensure we order the tables by their numerical ID for consistent and
        # understandable back-up ordering.
        cursor.execute(
            """SELECT CONCAT(table_schema, '.', table_name)
    FROM information_schema.tables
    WHERE table_name ~ %(table_prefix_regex_escaped)s  or
          table_name ~ %(through_table_regex_escaped)s or
          table_name ~ %(multipleselect_table_regex_escaped)s
    ORDER BY table_schema,
             substring(table_name FROM '[a-zA-Z]+'),
             substring(table_name FROM '[0-9]+')::int""",
            {
                "table_prefix_regex_escaped": f"^{table_prefix_regex_escaped}.*$",
                "through_table_regex_escaped": f"^{through_table_regex_escaped}.*$",
                "multipleselect_table_regex_escaped": f"^{multipleselect_table_regex_escaped}.*$",
            },
        )
        return [r[0] for r in cursor.fetchall()]


def _default_backup_location(database):
    now = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"baserow_backup_{database}_{now}.tar.gz"


def add_shared_postgres_command_args(parser):
    """
    The DB connection parameters are shared between the backup_baserow and
    restore_baserow commands.
    """

    parser.add_argument(
        "-h",
        "--host",
        type=str,
        required=True,
        dest="host",
        help="The host name of the machine on which the database is running.",
    )
    parser.add_argument(
        "-d",
        "--database",
        required=True,
        type=str,
        dest="database",
        help="Specifies the name of the database to connect to.",
    )
    parser.add_argument(
        "-U",
        "--username",
        required=True,
        type=str,
        dest="username",
        help="The username to connect to the database as.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=str,
        default="5432",
        dest="port",
        help="Specifies the TCP port or local Unix domain socket file on which "
        "the server is listening for connections.",
    )
