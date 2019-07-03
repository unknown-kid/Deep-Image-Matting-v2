import random

import torch
from torchvision import transforms
from tqdm import tqdm

from config import device, im_size
from data_gen import data_transforms, process, generate_trimap, random_choice, fg_test_files, bg_test_files
from utils import compute_mse, compute_sad, AverageMeter, get_logger
from utils import safe_crop


def gen_names():
    num_fgs = 50
    num_bgs = 1000
    num_bgs_per_fg = 20

    names = []
    bcount = 0
    for fcount in range(num_fgs):
        for i in range(num_bgs_per_fg):
            names.append(str(fcount) + '_' + str(bcount) + '.png')
            bcount += 1

    return names


if __name__ == '__main__':
    checkpoint = 'BEST_checkpoint.tar'
    checkpoint = torch.load(checkpoint)
    model = checkpoint['model']
    model = model.to(device)
    model.eval()

    transformer = data_transforms['valid']

    names = gen_names()

    mse_losses = AverageMeter()
    sad_losses = AverageMeter()

    logger = get_logger()

    for i, name in tqdm(enumerate(names)):
        fcount = int(name.split('.')[0].split('_')[0])
        bcount = int(name.split('.')[0].split('_')[1])
        im_name = fg_test_files[fcount]
        bg_name = bg_test_files[bcount]
        img, alpha, fg, bg = process(im_name, bg_name)

        # crop size 320:640:480 = 1:1:1
        different_sizes = [(320, 320), (480, 480), (640, 640)]
        crop_size = random.choice(different_sizes)

        trimap = generate_trimap(alpha)
        x, y = random_choice(trimap, crop_size)
        img = safe_crop(img, x, y, crop_size)
        alpha = safe_crop(alpha, x, y, crop_size)

        trimap = generate_trimap(alpha)

        x = torch.zeros((4, im_size, im_size), dtype=torch.float)
        img = transforms.ToPILImage()(img)
        img = transformer(img)
        x[0:3, :, :] = img
        x[3, :, :] = torch.from_numpy(trimap.copy()) / 255.

        img = torch.from_numpy(x)

        # Move to GPU, if available
        img = img.type(torch.FloatTensor).to(device)  # [N, 3, 320, 320]
        alpha = alpha / 255.

        # Forward prop.
        pred = model(img)  # [1, 320, 320]
        pred = pred.cpu().numpy()
        pred = pred.reshape((im_size, im_size))  # [320, 320]

        # Calculate loss
        # loss = criterion(alpha_out, alpha_label)
        mse_loss = compute_mse(pred, alpha, trimap)
        sad_loss = compute_sad(pred, alpha)

        # Keep track of metrics
        mse_losses.update(mse_loss.item())
        sad_losses.update(sad_loss.item())

    print("sad:{} mse:{}".format(sad_losses.avg, mse_losses.avg))