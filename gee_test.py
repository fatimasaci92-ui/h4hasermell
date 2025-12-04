import ee

# Essayer d'initialiser GEE
try:
    ee.Initialize()
    print("Connexion GEE OK ✅")
except Exception as e:
    print("Authentification requise...")
    ee.Authenticate()  # ouvre un navigateur pour te connecter
    ee.Initialize()
    print("Connexion GEE OK après authentification ✅")
