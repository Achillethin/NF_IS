#!/usr/bin/env python3

import os
import sys
import json
import glob
import shutil

import torch

from tensorboardX import SummaryWriter

import tqdm

from lgf.experiment import load_run, num_params


def get_config(path):
    with open(f"{path}/config.json", "r") as f:
        return json.load(f)


def get_configs(root):
    return [get_config(p) for p in glob.glob(f"{root}/*")]


def all_keys(configs):
    result = []
    for c in configs:
        result += list(c)
    return list(set(result))


def should_ignore_key(key):
    return key in ["seed", "schema_type"]


def differing_keys(root):
    configs = get_configs(root)

    result = []
    for k in all_keys(configs):
        if not should_ignore_key(k) and key_value_differs(k, configs):
            result.append(k)

    return result


def key_value_differs(key, configs):
    if key not in configs[0]:
        return True

    val = configs[0][key]

    for c in configs:
        if key not in c or c[key] != val:
            return True

    return False


def get_config_values(keys, path):
    config = get_config(path)

    result = {}
    for k in keys:
        val = config.get(k)
        result[k] = simplify_value(val)

    return result


def simplify_value(val):
    if isinstance(val, list):
        items = set(val)
        if len(items) == 1:
            item, = items
            return f"[{item}]*{len(val)}"
        else:
            return f"[{','.join(items)}]"
    elif val is None:
        return "None"
    else:
        return val


def group_runs(root):
    keys = differing_keys(model_dir)

    groups = {}
    for run in glob.glob(f"{root}/*"):
        differing_config_dict = get_config_values(keys, run)
        vals = tuple([differing_config_dict[k] for k in keys])
        groups.setdefault(vals, []).append(run)

    return list(groups.values())


root = sys.argv[1]

keys = differing_keys(root)

for path in tqdm.tqdm(glob.glob(f"{root}/*")):
    vals = get_config_values(keys, path)

    density, x_train, x_valid, x_test, config, checkpoint = load_run(
        run_dir=path,
        device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    )

    density.eval()
    with torch.no_grad():
        all_metrics = density.metrics(x_test, num_elbo_samples=100)

    metrics = {
        "log-prob": all_metrics["log-prob"].mean().item(),
        "elbo-gap": all_metrics["elbo-gap"].mean().item(),
        "epoch": checkpoint["epoch"],
        "num-params": num_params(density)
    }

    writer = SummaryWriter(logdir=path)
    writer.add_hparams(hparam_dict=vals, metric_dict=metrics)


for path in glob.glob(f"{root}/*"):
    dataset = get_config(path)["dataset"]
    dataset_dir = f"{os.path.dirname(path)}/{dataset}"
    os.makedirs(dataset_dir, exist_ok=True)
    shutil.move(path, dataset_dir)


for path in glob.glob(f"{root}/*/*"):
    model = get_config(path)["model"]
    model_dir = f"{os.path.dirname(path)}/{model}"
    os.makedirs(model_dir, exist_ok=True)
    shutil.move(path, model_dir)


for model_dir in glob.glob(f"{root}/*/*"):
    groups = group_runs(model_dir)

    for i, group in enumerate(groups):
        group_dir = f"{model_dir}/{i}"
        os.makedirs(group_dir)
        for run in group:
            shutil.move(run, group_dir)
