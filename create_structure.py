import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

structure = {
    ".env": "",
    "requirements.txt": "",
    "app": {
        "__init__.py": "",
        "main.py": "",
        "core": {
            "__init__.py": "",
            "config.py": ""
        },
        "db": {
            "__init__.py": "",
            "supabase.py": ""
        },
        "models": {
            "__init__.py": "",
            "schemas.py": ""
        },
        "services": {
            "__init__.py": "",
            "feature_builder.py": "",
            "rl_model.py": ""
        },
        "api": {
            "__init__.py": "",
            "endpoints.py": ""
        }
    }
}


def create_structure(base_path, struct):
    for name, content in struct.items():
        path = os.path.join(base_path, name)

        if isinstance(content, dict):
            os.makedirs(path, exist_ok=True)
            create_structure(path, content)
        else:
            if not os.path.exists(path):
                with open(path, "w") as f:
                    f.write(content)


if __name__ == "__main__":
    create_structure(BASE_DIR, structure)
    print("Project structure created successfully.")
