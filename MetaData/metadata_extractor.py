"""
Модуль для извлечения метаданных из файлов
"""

import os
from pathlib import Path
from typing import Dict, Any
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import logging

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Класс для извлечения метаданных"""

    @staticmethod
    def extract_photo_metadata(file_path: str) -> Dict[str, Any]:
        """Извлечение метаданных из фото"""
        result = {
            'camera_info': {},
            'photo_settings': {},
            'gps': {},
            'datetime': None,
            'basic': {},
            'diagnostics': {
                'has_exif': False,
                'exif_tags_count': 0
            }
        }

        try:
            logger.info(f"Открываю файл: {file_path}")
            with Image.open(file_path) as img:
                # Базовая информация
                result['basic'] = {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format
                }
                logger.info(f"Изображение: {img.width}x{img.height}, формат: {img.format}")

                # Извлечение EXIF
                try:
                    exif_data = img._getexif()
                    logger.info(f"EXIF данные: {exif_data is not None}")
                except Exception as e:
                    logger.error(f"Ошибка получения EXIF: {e}")
                    exif_data = None

                if exif_data:
                    result['diagnostics']['has_exif'] = True
                    result['diagnostics']['exif_tags_count'] = len(exif_data)
                    logger.info(f"Найдено {len(exif_data)} EXIF тегов")

                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)

                        # Камера/телефон
                        if tag == 'Make':
                            result['camera_info']['make'] = str(value).strip()
                            logger.info(f"Make: {value}")
                        elif tag == 'Model':
                            result['camera_info']['model'] = str(value).strip()
                            logger.info(f"Model: {value}")
                        elif tag == 'Software':
                            result['camera_info']['software'] = str(value).strip()

                        # Настройки съемки
                        elif tag == 'ISOSpeedRatings':
                            result['photo_settings']['iso'] = int(value) if isinstance(value, int) else str(value)
                        elif tag == 'FNumber':
                            try:
                                if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                                    f_number = value.numerator / value.denominator
                                else:
                                    f_number = float(value)
                                result['photo_settings']['aperture'] = f"f/{f_number:.1f}"
                            except:
                                result['photo_settings']['aperture'] = str(value)
                        elif tag == 'ExposureTime':
                            try:
                                if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                                    exp = value.numerator / value.denominator
                                else:
                                    exp = float(value)

                                if exp >= 1:
                                    result['photo_settings']['exposure'] = f"{exp:.1f}с"
                                else:
                                    result['photo_settings']['exposure'] = f"1/{int(1/exp)}с"
                            except:
                                result['photo_settings']['exposure'] = str(value)
                        elif tag == 'FocalLength':
                            try:
                                if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                                    focal = value.numerator / value.denominator
                                else:
                                    focal = float(value)
                                result['photo_settings']['focal_length'] = f"{focal:.1f}mm"
                            except:
                                result['photo_settings']['focal_length'] = str(value)
                        elif tag == 'LensModel':
                            result['photo_settings']['lens'] = str(value).strip()
                        elif tag == 'WhiteBalance':
                            result['photo_settings']['white_balance'] = 'Авто' if value == 0 else 'Ручной'
                        elif tag == 'Flash':
                            flash_map = {
                                0: 'Не сработала',
                                1: 'Сработала',
                                8: 'Авто',
                                9: 'Сработала, авто',
                                16: 'Не сработала',
                                24: 'Авто'
                            }
                            result['photo_settings']['flash'] = flash_map.get(value, str(value))

                        # Дата и время
                        elif tag in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                            if value:
                                result['datetime'] = str(value)

                        # GPS данные
                        elif tag == 'GPSInfo':
                            try:
                                gps_data = {}
                                for gps_tag_id, gps_value in value.items():
                                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                                    gps_data[gps_tag] = gps_value

                                if 'GPSLatitude' in gps_data and 'GPSLongitude' in gps_data:
                                    lat = MetadataExtractor._convert_to_degrees(gps_data['GPSLatitude'])
                                    lon = MetadataExtractor._convert_to_degrees(gps_data['GPSLongitude'])

                                    if gps_data.get('GPSLatitudeRef') == 'S':
                                        lat = -lat
                                    if gps_data.get('GPSLongitudeRef') == 'W':
                                        lon = -lon

                                    result['gps'] = {
                                        'latitude': lat,
                                        'longitude': lon,
                                        'google_maps': f"https://www.google.com/maps?q={lat},{lon}",
                                        'yandex_maps': f"https://yandex.ru/maps/?pt={lon},{lat}&z=15",
                                        'osm': f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
                                    }
                                    logger.info(f"GPS найден: {lat}, {lon}")
                            except Exception as e:
                                logger.error(f"Ошибка обработки GPS: {e}")
                else:
                    logger.warning("EXIF данные отсутствуют")

        except Exception as e:
            logger.error(f"Ошибка при обработке фото: {e}")
            result['error'] = str(e)

        return result

    @staticmethod
    def _convert_to_degrees(value) -> float:
        """Конвертация GPS координат"""
        if isinstance(value, tuple) and len(value) >= 3:
            try:
                d = float(value[0].numerator) / float(value[0].denominator)
                m = float(value[1].numerator) / float(value[1].denominator)
                s = float(value[2].numerator) / float(value[2].denominator)
                return d + (m / 60.0) + (s / 3600.0)
            except:
                return 0.0
        return 0.0

    @staticmethod
    def extract_audio_metadata(file_path: str) -> Dict[str, Any]:
        """Извлечение метаданных из аудио"""
        result = {
            'basic': {},
            'tags': {}
        }

        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            if audio:
                info = {}
                if hasattr(audio.info, 'length'):
                    length_sec = int(audio.info.length)
                    mins = length_sec // 60
                    secs = length_sec % 60
                    info['duration'] = f"{mins:02d}:{secs:02d}"

                if hasattr(audio.info, 'bitrate'):
                    info['bitrate'] = f"{audio.info.bitrate // 1000} kbps"

                if hasattr(audio.info, 'sample_rate'):
                    info['sample_rate'] = f"{audio.info.sample_rate // 1000} kHz"

                result['basic'] = info

                # Теги
                if hasattr(audio, 'tags') and audio.tags:
                    tags = {}
                    tag_mapping = {
                        'title': 'Название',
                        'artist': 'Исполнитель',
                        'album': 'Альбом',
                        'date': 'Год',
                        'genre': 'Жанр',
                        'tracknumber': 'Трек',
                        'comment': 'Комментарий'
                    }

                    for key, value in audio.tags.items():
                        clean_key = key.lower().replace('©', '').replace('----:com.apple.itunes:', '')
                        if isinstance(value, list):
                            value = value[0] if value else ''
                        if isinstance(value, bytes):
                            try:
                                value = value.decode('utf-8', errors='ignore')
                            except:
                                value = str(value)

                        display_key = tag_mapping.get(clean_key, clean_key.title())
                        if str(value).strip():
                            tags[display_key] = str(value)

                    result['tags'] = tags
        except Exception as e:
            logger.error(f"Ошибка при обработке аудио: {e}")
            result['error'] = str(e)

        return result

    @staticmethod
    def extract_pdf_metadata(file_path: str) -> Dict[str, Any]:
        """Извлечение метаданных из PDF"""
        result = {
            'basic': {},
            'info': {}
        }

        try:
            import PyPDF2
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                result['basic'] = {
                    'pages': len(pdf_reader.pages),
                    'encrypted': 'Да' if pdf_reader.is_encrypted else 'Нет'
                }

                if pdf_reader.metadata:
                    for key, value in pdf_reader.metadata.items():
                        if value:
                            clean_key = key.replace('/', '').title()
                            result['info'][clean_key] = str(value)
        except Exception as e:
            logger.error(f"Ошибка при обработке PDF: {e}")
            result['error'] = str(e)

        return result


def get_location_description(lat: float, lon: float) -> str:
    """Получение описания местоположения"""
    locations = [
        (59.9343, 30.3351, "Санкт-Петербург, Россия"),
        (55.7558, 37.6173, "Москва, Россия"),
        (41.0082, 28.9784, "Стамбул, Турция"),
        (48.8566, 2.3522, "Париж, Франция"),
        (51.5074, -0.1278, "Лондон, Великобритания"),
        (40.7128, -74.0060, "Нью-Йорк, США"),
        (35.6762, 139.6503, "Токио, Япония"),
        (-33.8688, 151.2093, "Сидней, Австралия"),
    ]

    min_distance = float('inf')
    nearest = None

    for loc_lat, loc_lon, name in locations:
        distance = ((lat - loc_lat) ** 2 + (lon - loc_lon) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            nearest = name

    if nearest and min_distance < 2.0:
        return nearest
    else:
        return f"{'Северное' if lat > 0 else 'Южное'} полушарие"


def format_photo_response(metadata: Dict[str, Any]) -> str:
    """Красивое форматирование метаданных фото"""
    lines = []

    lines.append("📸 **РЕЗУЛЬТАТ АНАЛИЗА ФОТО**")
    lines.append("")

    # Камера/Телефон
    camera = metadata.get('camera_info', {})
    if camera:
        lines.append(f"📷 **Устройство:**")
        if camera.get('make') and camera.get('model'):
            lines.append(f"   `{camera['make']} {camera['model']}`")
        elif camera.get('model'):
            lines.append(f"   `{camera['model']}`")
        elif camera.get('make'):
            lines.append(f"   `{camera['make']}`")
        if camera.get('software'):
            lines.append(f"   🔧 Программа: `{camera['software']}`")
        lines.append("")

    # Настройки съемки
    settings = metadata.get('photo_settings', {})
    if settings:
        lines.append(f"⚙️ **Настройки съемки:**")
        if settings.get('exposure'):
            lines.append(f"   ⏱ Выдержка: `{settings['exposure']}`")
        if settings.get('aperture'):
            lines.append(f"   🔆 Диафрагма: `{settings['aperture']}`")
        if settings.get('iso'):
            lines.append(f"   📊 ISO: `{settings['iso']}`")
        if settings.get('focal_length'):
            lines.append(f"   🔭 Фокусное: `{settings['focal_length']}`")
        if settings.get('lens'):
            lines.append(f"   📷 Объектив: `{settings['lens']}`")
        if settings.get('white_balance'):
            lines.append(f"   ⚪️ Баланс белого: `{settings['white_balance']}`")
        if settings.get('flash'):
            lines.append(f"   💡 Вспышка: `{settings['flash']}`")
        lines.append("")

    # Дата и время
    if metadata.get('datetime'):
        lines.append(f"🕐 **Дата и время съемки:**")
        lines.append(f"   `{metadata['datetime']}`")
        lines.append("")

    # GPS координаты
    gps = metadata.get('gps', {})
    if gps and 'latitude' in gps and 'longitude' in gps:
        lat = gps['latitude']
        lon = gps['longitude']

        lines.append(f"📍 **МЕСТОПОЛОЖЕНИЕ**")
        lines.append("")
        lines.append(f"   🌐 Координаты:")
        lines.append(f"      Широта: `{lat:.6f}`")
        lines.append(f"      Долгота: `{lon:.6f}`")

        location_desc = get_location_description(lat, lon)
        lines.append("")
        lines.append(f"   🏙 **Примерное место:**")
        lines.append(f"      {location_desc}")

        lines.append("")
        lines.append(f"   🗺 **Открыть на картах:**")
        lines.append(f"      • [Google Maps]({gps['google_maps']})")
        lines.append(f"      • [Яндекс Карты]({gps['yandex_maps']})")
        lines.append(f"      • [OpenStreetMap]({gps['osm']})")
        lines.append("")

    # Базовая информация
    basic = metadata.get('basic', {})
    if basic:
        lines.append(f"ℹ️ **Информация о файле:**")
        if basic.get('width') and basic.get('height'):
            lines.append(f"   📐 Разрешение: `{basic['width']}×{basic['height']}`")
        if basic.get('format'):
            lines.append(f"   📁 Формат: `{basic['format']}`")
        lines.append("")

    # Если нет данных
    if not camera and not settings and not gps and not metadata.get('datetime'):
        lines.append("⚠️ **Метаданные не найдены**")
        lines.append("")
        lines.append("Возможные причины:")
        lines.append("• Фото отправлено как изображение, а не файл")
        lines.append("• Фото обработано через соцсеть (Telegram, Instagram, VK)")
        lines.append("• Это скриншот или сжатое изображение")
        lines.append("• Метаданные удалены вручную")

    return '\n'.join(lines)


def format_audio_response(metadata: Dict[str, Any]) -> str:
    """Форматирование метаданных аудио"""
    lines = []

    lines.append("🎵 **РЕЗУЛЬТАТ АНАЛИЗА АУДИО**")
    lines.append("")

    # Теги
    tags = metadata.get('tags', {})
    if tags:
        lines.append("📝 **Информация о треке:**")
        for key, value in tags.items():
            if value and str(value).strip():
                lines.append(f"   • {key}: `{value}`")
        lines.append("")

    # Базовая информация
    basic = metadata.get('basic', {})
    if basic:
        lines.append("🎛 **Технические характеристики:**")
        if basic.get('duration'):
            lines.append(f"   ⏱ Длительность: `{basic['duration']}`")
        if basic.get('bitrate'):
            lines.append(f"   📊 Битрейт: `{basic['bitrate']}`")
        if basic.get('sample_rate'):
            lines.append(f"   🎚 Частота: `{basic['sample_rate']}`")
        lines.append("")

    return '\n'.join(lines)


def format_pdf_response(metadata: Dict[str, Any]) -> str:
    """Форматирование метаданных PDF"""
    lines = []

    lines.append("📄 **РЕЗУЛЬТАТ АНАЛИЗА PDF**")
    lines.append("")

    # Основная информация
    basic = metadata.get('basic', {})
    if basic:
        lines.append("📊 **Информация о документе:**")
        if basic.get('pages'):
            lines.append(f"   📄 Страниц: `{basic['pages']}`")
        if basic.get('encrypted'):
            lines.append(f"   🔒 Зашифрован: `{basic['encrypted']}`")
        lines.append("")

    # Метаданные
    info = metadata.get('info', {})
    if info:
        lines.append("📋 **Метаданные:**")
        for key, value in info.items():
            if value and str(value).strip():
                lines.append(f"   • {key}: `{value}`")
        lines.append("")

    return '\n'.join(lines)