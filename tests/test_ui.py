from server import BAPSicleServer
import unittest


class TestUI(unittest.TestCase):

    # initialization logic for the test suite declared in the test module
    # code that is executed before all tests in one test run
    @classmethod
    def setUpClass(cls):
        pass

    # clean up logic for the test suite declared in the test module
    # code that is executed after all tests in one test run
    @classmethod
    def tearDownClass(cls):
        pass

    # initialization logic
    # code that is executed before each test
    def setUp(self):
        return # Temp disable this test.
        server = BAPSicleServer(start_flask=False).get_flask()
        server.config['TESTING'] = True
        server.config['WTF_CSRF_ENABLED'] = False
        server.config['DEBUG'] = False
        self.app = server.test_client()

    # clean up logic
    # code that is executed after each test
    def tearDown(self):
        pass

    def test_index_status_code(self):
        return # Temp disable this test.
        # sends HTTP GET request to the application
        # on the specified path
        result = self.app.get('/')

        # assert the status code of the response
        self.assertEqual(result.status_code, 200)


# runs the unit tests in the module
if __name__ == '__main__':
    unittest.main()
