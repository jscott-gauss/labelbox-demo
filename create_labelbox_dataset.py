import labelbox
import boto3
import argparse
from random import shuffle
import itertools
import tqdm


def replace_chars(input_string):
    char_replacement = {"<": "%3C", ">": "%3E", "[": "%5B", "]": "%5D"}
    for char in char_replacement.keys():
        input_string = input_string.replace(char, char_replacement[char])

    return input_string


def add_images(s3: boto3.resource, bucket_name: str, prefix: str, num_images=None):

    """
    Create the data_rows dictionary to be used with the Labelbox client to 
    create a new dataset.

    @param s3: A boto3.resource("s3") object
    @param bucket_name: Name of the bucket that is properly credentialed to work with labelbox
    @param prefix: The prefix (subfolder) after bucket_name that contains the "folder" of images to add

    @return data_rows: A dictionary object where each entry is an image to be added to the dataset
    """
    all_images = list(bucket.objects.filter(Prefix=prefix))
    shuffle(all_images)

    if num_images is not None:
        all_images = all_images[:num_images]

    data_rows = []
    for item in tqdm.tqdm(all_images):
        data_rows.append(
            {
                "row_data": f"https://{bucket_name}.s3.us-west-2.amazonaws.com/{replace_chars(item.key)}",
                "external_id": f"{item.key}",
            }
        )

    return data_rows


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Create labelbox dataset")
    parser.add_argument(
        "dataset_name", type=str, help="Name of the dataset on labelbox"
    )
    parser.add_argument(
        "--bucket-name", type=str, default="gauss-labelbox-data", help="S3 bucket name"
    )

    parser.add_argument("--s3-prefix", type=str, help="S3 prefix/folder of images")
    parser.add_argument("--append-to-dataset", type=str, default=None, help="Labelbox ID of the dataset to append to")
    parser.add_argument("--num-images", type=int, default=None, help="number of images (defaults to all)")

    args = parser.parse_args()

    # Create Labelbox client
    lb = labelbox.Client()
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(args.bucket_name)
    data_rows = add_images(
        s3, args.bucket_name, args.s3_prefix, num_images=args.num_images
    )

    if args.append_to_dataset is None:
        info = f"""
        Creating dataset:
            Labelbox Name: {args.dataset_name}
            S3 Location: s3://{args.bucket_name}/{args.s3_prefix}
            Num images: {args.num_images}
        """
        print(info)

        dataset = lb.create_dataset(name=args.dataset_name)

        # Bulk add data rows to the dataset
        task = dataset.create_data_rows(data_rows)
        task.wait_till_done()
        print(task.status)

    else:
        dataset = lb.get_dataset(args.append_to_dataset)
        external_ids = [row.external_id for row in dataset.data_rows()]
        append_rows = []
        print('Filtering out existing external_ids')
        for row in data_rows:
            if row["external_id"] not in external_ids:
                append_rows.append(row)
                print(f"ADDING {row['external_id']}")
        
        if len(append_rows) > 0:
            # Bulk add data rows to the dataset
            print(f"Adding {len(append_rows)} to dataset {dataset.name}: {dataset.uid}")
            task = dataset.create_data_rows(append_rows)
            task.wait_till_done()
            print(task.status)