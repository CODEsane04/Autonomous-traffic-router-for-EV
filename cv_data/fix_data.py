import glob

# Get all label files
label_files = glob.glob('train/labels/*.txt')

# We only care about ambulance (4) and firetruck (5). We will map them to 0 and 1.
class_map = {4: 0, 5: 1, 6: 2}

count = 0
for file_path in label_files:
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5: 
            continue

        old_class = int(parts[0])
        if old_class not in class_map: 
            continue

        new_class = class_map[old_class]

        # Convert 8-point polygon to standard box
        if len(parts) == 9:
            coords = [float(x) for x in parts[1:]]
            xs = coords[0::2]
            ys = coords[1::2]
            
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            x_center = (min_x + max_x) / 2.0
            y_center = (min_y + max_y) / 2.0
            width = max_x - min_x
            height = max_y - min_y
            
            new_lines.append(f"{new_class} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
            count += 1

    # Overwrite the file with the fixed data
    with open(file_path, 'w') as f:
        f.writelines(new_lines)

# Create a clean data.yaml
yaml_content = """train: train/images
val: train/images

nc: 3
names: ['ambulance', 'firetruck', 'other_vehicle']
"""
with open('data.yaml', 'w') as f:
    f.write(yaml_content)

print(f"Success! Fixed {count} bounding boxes and generated a clean data.yaml.")
