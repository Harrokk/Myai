"""No network or installations; mock Python distribution metadata only."""
import importlib.metadata as metadata

from scripts import ventuno_installed_dependency_metadata_readonly as scan


def test_healthy_allowlisted_versions_are_not_release_approval():
    versions = {name: "2.0.0" for name in scan.TRACKED}
    versions["requests"] = "2.34.2"
    versions["urllib3"] = "2.8.0"
    report = scan.observe(lookup=versions.__getitem__, package_count=54)
    assert report["network_dependency_policy_observed"] is True
    assert report["usual_voice_package_count"] == 4
    assert report["environment_distribution_count"] == 54
    assert report["production_deployment_authorized"] is False
    assert report["physical_hardware_test_performed"] is False
    assert report["all_transitive_dependencies_resolved"] is False


def test_outdated_installed_network_stack_cannot_pass_readiness():
    def old(name):
        if name == "requests":
            return "2.32.5"
        if name == "urllib3":
            return "2.7.0"
        raise metadata.PackageNotFoundError(name)
    report = scan.observe(lookup=old, package_count=3)
    assert report["network_dependency_policy_observed"] is False
    assert report["patched_network_dependency_floors_observed"] == {
        "requests": False, "urllib3": False
    }
    assert report["usual_voice_package_count"] == 0
    assert report["status"] == "read-only-installed-dependency-inventory"


def test_pre_release_and_untrusted_metadata_are_not_security_proof():
    def invalid(name):
        if name == "requests":
            return "2.33.0rc1"
        if name == "urllib3":
            return "/home/private/account/token"
        raise metadata.PackageNotFoundError(name)
    report = scan.observe(lookup=invalid, package_count=7)
    assert report["network_dependency_policy_observed"] is False
    assert report["allowlisted_installed_versions"]["urllib3"] == "unverified-version-metadata"
    assert "/home/private" not in str(report)


def test_not_found_is_not_construed_as_patched():
    report = scan.observe(
        lookup=lambda name: (_ for _ in ()).throw(metadata.PackageNotFoundError(name)),
        package_count=0,
    )
    assert report["usual_voice_package_count"] == 0
    assert report["network_dependency_policy_observed"] is False
    assert all(value is None for value in report["allowlisted_installed_versions"].values())
