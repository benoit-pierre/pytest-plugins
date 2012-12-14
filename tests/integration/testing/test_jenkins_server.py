import os.path
from pytest import raises

from mock import patch

import pkglib.testing.pytest.jenkins_server as pj

# patch out any changes you want to the Jenkins server here:
# These are once-for-all changes!

this_dir = os.path.dirname(__file__)
PLUGIN_REPO = os.path.join(this_dir, 'jenkins_plugins')

def pre_setup(jenkins_server):
    pass

# this builds the session server, so you have to have deone any pre_setup and post_setup
# before this line
pj.JenkinsTestServer.pre_setup = pre_setup

from pkglib.testing.pytest.jenkins_server import pytest_funcarg__jenkins_server

def test_load_plugins_fails_with_invalid_repo(jenkins_server):
    with raises(ValueError) as e:
        jenkins_server.load_plugins('junk_repo_name')
    assert str(e.value) == 'Plugin repository "junk_repo_name" does not exist'

def test_load_plugins_fails_with_invalid_plugin_name_as_string(jenkins_server):
    with raises(ValueError) as e:
        jenkins_server.load_plugins(PLUGIN_REPO, 'junk')
    assert str(e.value) == 'Plugin "junk" is not present in the repository'

def test_load_plugins_fails_with_invalid_plugin_name_as_list(jenkins_server):
    with raises(ValueError)as e:
        jenkins_server.load_plugins(PLUGIN_REPO, ['junk'])
    assert str(e.value) == 'Plugin "junk" is not present in the repository'

def test_load_plugins_fails_with_invalid_plugin_name_no_duplicates_in_error_msg(jenkins_server):
    with raises(ValueError) as e:
        jenkins_server.load_plugins(PLUGIN_REPO, ['junk', 'junk'])
    assert str(e.value) == 'Plugin "junk" is not present in the repository'

def test_load_plugins_fails_with_invalid_plugin_names_as_list(jenkins_server):
    with raises(ValueError)as e:
        jenkins_server.load_plugins(PLUGIN_REPO, ['zjunk', 'junk'])
    assert str(e.value) == "Plugins ['junk', 'zjunk'] are not present in the repository"

def test_load_plugins_loads_only_nominated_plugins(jenkins_server):
    with patch('pkglib.testing.jenkins_server.shutil.copy') as mock_copy:
        jenkins_server.load_plugins(PLUGIN_REPO, 'notification')
        assert mock_copy.call_count == 1
        tup = mock_copy.call_args_list[0][0]
        assert tup[0].endswith('jenkins_plugins/notification.hpi')
        assert str(tup[1]) == os.path.join(jenkins_server.workspace, 'plugins/notification.hpi')

def test_load_plugins_loads_all_plugins(jenkins_server):
    with patch('pkglib.testing.jenkins_server.shutil.copy') as mock_copy:
        jenkins_server.load_plugins(PLUGIN_REPO)
        assert mock_copy.call_count == len([x for x in os.listdir(PLUGIN_REPO) if x.endswith('.hpi')])

def test_jenkins_pre_server(jenkins_server):
    """ Creates template, creates the jenkins job
    """
    assert jenkins_server.check_server_up()
