import click

@click.command("standalone")
@click.option('--exp_config', type=str, required=True, multiple=True)
def try_dray1(exp_config):
    print(len(exp_config))
    for config in exp_config:
        print(config)
    
    print("Trying Dray1")

if __name__ == "__main__":
    try_dray1()