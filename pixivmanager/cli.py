import os
import time
import sys
from pathlib import Path

import click

from . import exceptions
from .config import Config
from .downloader import PixivDownloader
from .models import DatabaseHelper
from .pixivapi import PixivAPI
from .helpers import init_colorama


@click.command()
@click.argument(
    'download_type', type=click.Choice(('bookmark', 'works', 'daemon')))
@click.option(
    '--user',
    default=0,
    type=click.INT,
    help='User to download. Default is the current user.')
@click.option(
    '--max', 'max_times', default=None, type=click.INT, help='Max get times.')
@click.option('--private', is_flag=True, help='Download private bookmarks.')
@click.option(
    '--type',
    'works_type',
    default=None,
    type=click.STRING,
    help='Works type to download.\
    \nCan be illusts / manga / ugoira.')
@click.option(  #TODO https://click-docs-zh-cn.readthedocs.io/zh/latest/options.html
    '--tags-include',
    default=None,
    type=click.STRING,
    help='Download works by tags. Split by ;')
@click.option(
    '--tags-exclude',
    default=None,
    type=click.STRING,
    help='Exclude works by tags. Split by ;')
@click.option('--echo', is_flag=True, help='Echo database script')
@click.option(
    '--config',
    default=None,
    type=click.STRING,
    help='Config JSON file, default: ~/.pixivmanager-python/config.json')
def main(user, max_times, private, download_type, works_type, tags_include,
         tags_exclude, echo, config):
    '''
    CLI for PixivManager.
    '''
    root_path: Path = Path.home() / '.pixivmanager-python'
    if not config:
        os.makedirs(root_path, exist_ok=True)

    config_path = config or root_path / 'config.json'
    config = Config(config_path)
    if os.name == 'nt':
        init_colorama()
    logger = config.get_logger('CLI')
    logger.info('Config file: %s' % config_path)

    if download_type == 'daemon':
        from .daemon import main as daemon_main
        daemon_main(config)
        return

    try:
        tags_include = None if not tags_include else set(
            tags_include.split(';'))
        tags_exclude = None if not tags_exclude else set(
            tags_exclude.split(';'))
    except:
        print('Value USER | MAX | DOWNLOAD_TYPE must be INT.')
        exit(-1)

    papi = PixivAPI(
        language=config.cfg['pixiv']['language'],
        logger=config.get_logger('PixivAPI'))

    login_result = None

    def login_with_pw():
        import getpass
        username = input('E-mail / Pixiv ID: ')
        password = getpass.getpass()
        return papi.login(username, password)

    try:
        refresh_token = config.cfg['pixiv']['refresh_token']
        if refresh_token:
            login_result = papi.login(refresh_token=refresh_token)
        else:
            login_result = login_with_pw()
    except exceptions.LoginTokenError:
        login_result = login_with_pw()
    except exceptions.LoginPasswordError:
        click.echo('Username / password error!')

    if not login_result:
        exit(-1)

    config.cfg['pixiv']['refresh_token'] = papi.refresh_token
    config.save_cfg()
    pdb = DatabaseHelper(config.database_uri, echo=echo)
    pdl = PixivDownloader(
        config.pixiv_works_dir, logger=config.get_logger('PixivDownloader'))
    if download_type == 'bookmarks':
        logger.info('Downloading all bookmarks...')
    elif download_type == 'works':
        logger.info('Downloading user\'s works...')
    if not user:
        user = papi.pixiv_user_id
    session = pdb.sessionmaker()
    pdl.all_works(download_type, papi, session, user, max_times, works_type,
                  tags_include, tags_exclude)

    while pdl.unfinished_tasks:
        # Wait until all tasks done.
        time.sleep(0.1)

    pdl.dq.join()
    logger.info('Works download task done! User ID: %s' % papi.pixiv_user_id)


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
