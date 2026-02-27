import prisma from '../models';
import { NotFoundError } from '../middleware/errorHandler';

export class SettingsService {
  async getSettings(userId: string) {
    let settings = await prisma.userSettings.findUnique({ where: { userId } });
    if (!settings) {
      settings = await prisma.userSettings.create({ data: { userId } });
    }
    return settings;
  }

  async updateSettings(userId: string, data: {
    theme?: string;
    defaultLLMConfigId?: string;
    emailNotifications?: boolean;
    browserNotifications?: boolean;
    executionTimeout?: number;
    screenshotInterval?: number;
    sandboxMode?: boolean;
    autoSaveResults?: boolean;
    dailyIdleTokenLimit?: number;
  }) {
    const settings = await prisma.userSettings.upsert({
      where: { userId },
      create: { userId, ...data },
      update: data,
    });
    return settings;
  }

  async getNotifications(userId: string, page = 1, limit = 20) {
    const skip = (page - 1) * limit;
    const [notifications, total, unreadCount] = await Promise.all([
      prisma.notification.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.notification.count({ where: { userId } }),
      prisma.notification.count({ where: { userId, read: false } }),
    ]);
    return {
      notifications,
      total,
      unreadCount,
      page,
      limit,
    };
  }

  async markNotificationRead(notificationId: string, userId: string) {
    const notification = await prisma.notification.findUnique({ where: { id: notificationId } });
    if (!notification || notification.userId !== userId) throw new NotFoundError('Notification');

    return prisma.notification.update({
      where: { id: notificationId },
      data: { read: true },
    });
  }

  async markAllNotificationsRead(userId: string) {
    await prisma.notification.updateMany({
      where: { userId, read: false },
      data: { read: true },
    });
  }

  async deleteNotification(notificationId: string, userId: string) {
    const notification = await prisma.notification.findUnique({ where: { id: notificationId } });
    if (!notification || notification.userId !== userId) throw new NotFoundError('Notification');
    await prisma.notification.delete({ where: { id: notificationId } });
  }
}

export const settingsService = new SettingsService();
