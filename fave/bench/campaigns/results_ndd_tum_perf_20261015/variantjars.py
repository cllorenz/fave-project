""" pytest plugin: point the in-process JVM at the variant jars. """
import apkeep.lib_apkeep as la, apkeep.lib_ndd as ln
la._APKEEP_JAR = "/tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/ndd-variant/apkeep/target/apkeep-1.0.0.jar"
la._NDD_JAR = "/tmp/claude-1000/-home-ubuntu-fave-project/9c0634c3-9d13-4de9-addb-00b10f22f12f/scratchpad/ndd-variant/ndd/target/ndd-1.0.1-jar-with-dependencies.jar"
ln._NDD_JAR = la._NDD_JAR
ln._APKEEP_JAR = la._APKEEP_JAR

def pytest_sessionfinish(session, exitstatus):
    import jpype
    if not jpype.isJVMStarted():
        print('\nno JVM in this process'); return
    c = jpype.JClass('apkeep.ndd.NddPorts').class_
    print("\nNddPorts from", c.getProtectionDomain().getCodeSource().getLocation())
