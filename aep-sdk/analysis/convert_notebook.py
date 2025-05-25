import jupytext
import argparse
import pathlib

def convert_notebook(input_path_str: str, output_path_str: str = None):
    """
    Converts a file between Jupyter Notebook (.ipynb) and Markdown (.md) formats.

    If output_path_str is not provided, it will be inferred by changing
    the extension of the input_path_str.
    """
    input_path = pathlib.Path(input_path_str)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    input_suffix = input_path.suffix.lower()
    target_output_suffix = None

    if output_path_str:
        output_path = pathlib.Path(output_path_str)
        # Determine target_output_suffix from the provided output_path
        target_output_suffix = output_path.suffix.lower()
        if input_suffix == ".md" and target_output_suffix != ".ipynb":
            print(f"Warning: Input is Markdown ('{input_path}'), output should ideally be .ipynb. Forcing .ipynb extension for '{output_path}'.")
            output_path = output_path.with_suffix(".ipynb")
            target_output_suffix = ".ipynb"
        elif input_suffix == ".ipynb" and target_output_suffix != ".md":
            print(f"Warning: Input is Jupyter Notebook ('{input_path}'), output should ideally be .md. Forcing .md extension for '{output_path}'.")
            output_path = output_path.with_suffix(".md")
            target_output_suffix = ".md"
    else:
        if input_suffix == ".md":
            output_path = input_path.with_suffix(".ipynb")
            target_output_suffix = ".ipynb"
        elif input_suffix == ".ipynb":
            output_path = input_path.with_suffix(".md")
            target_output_suffix = ".md"
        else:
            raise ValueError(
                f"Unsupported input file type: {input_suffix}. "
                "Only .md and .ipynb are supported."
            )

    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] --- Conversion Attempt --- ")
    print(f"[INFO] Input: {input_path} ({input_suffix})")
    print(f"[INFO] Output: {output_path} ({target_output_suffix})")

    try:
        notebook = jupytext.read(input_path)
        print(f"[INFO] Successfully read input file: {input_path}")

        output_format_options = {}
        if input_suffix == ".ipynb" and target_output_suffix == ".md":
            output_format_options["fmt"] = "md:myst"
            output_format_options["outputs"] = True
            # NOTE on jupytext 1.17.1 and outputs:
            # Extensive testing showed that with jupytext 1.17.1, even with fmt="md:myst" 
            # and outputs=True, cell outputs (e.g., tracebacks) were NOT being written
            # to the .md file, despite being confirmed as read into memory.
            # This behavior might be version-specific or due to other environmental factors.
            # The .md file will be generated, but may not contain outputs as expected.
            print(f"[INFO] Converting IPYNB to MD: Using format 'md:myst' with outputs=True.")
            print(f"[INFO]   (Note: Output inclusion in .md with jupytext 1.17.1 may be limited based on tests.)")
        elif input_suffix == ".md" and target_output_suffix == ".ipynb":
            # For MD to IPYNB, jupytext default behavior is typically sufficient.
            # No explicit format or output options needed; it infers from output extension.
            print(f"[INFO] Converting MD to IPYNB: Using default jupytext behavior.")
        
        jupytext.write(notebook, output_path, **output_format_options)
        print(f"[INFO] Successfully converted '{input_path}' to '{output_path}'")

    except Exception as e:
        print(f"[ERROR] An error occurred during conversion: {e}")
        raise # Re-raise the exception to make script failure clear

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert between Jupyter Notebook (.ipynb) and Markdown (.md) files.\n" \
                    "Version Notes: Tested with jupytext 1.17.1. Output inclusion when converting\n" \
                    ".ipynb to .md (text-based) may be limited with this jupytext version."
    )
    parser.add_argument(
        "input_path",
        type=str,
        help="Path to the input file (.md or .ipynb)."
    )
    parser.add_argument(
        "--output_path",
        "-o",
        type=str,
        help="Optional path for the output file. If not provided, "
             "it's inferred from the input file name (e.g., input.md -> input.ipynb)."
    )

    args = parser.parse_args()

    try:
        convert_notebook(args.input_path, args.output_path)
    except FileNotFoundError as e:
        print(f"[ERROR] Input file not found: {e}")
        parser.print_help()
    except ValueError as e:
        print(f"[ERROR] Invalid input: {e}")
        parser.print_help()
    except Exception as e:
        print(f"[ERROR] A critical error occurred: {e}") 