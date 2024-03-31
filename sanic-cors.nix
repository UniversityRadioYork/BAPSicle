{ lib
, buildPythonPackage
, fetchPypi

, setuptools
, packaging
, sanic
 }:

buildPythonPackage rec {
  pname = "Sanic-Cors";
  version = "2.2.0";
  pyproject= true;

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-+NdRXaTIuDeHHUIsZjFMS1cEOWp4iUtZxQ4mqnKpWHM=";
  };

  nativeBuildInputs = [
    setuptools
  ];

  propagatedBuildInputs = [
    sanic
    packaging
  ];

  meta = with lib; {
    changelog = "https://github.com/ashleysommer/sanic-cors/releases/tag/${version}";
    description = "A Sanic extension for handling Cross Origin Resource Sharing (CORS), making cross-origin AJAX possible.";
    homepage = "https://github.com/ashleysommer/sanic-cors";
    license = licenses.mit;
    maintainers = with maintainers; [];
  };
}
