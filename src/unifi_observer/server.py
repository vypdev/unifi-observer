from .composition.bootstrap import create_app


def main() -> None:
    create_app().run(transport="streamable-http")


if __name__ == "__main__":
    main()
