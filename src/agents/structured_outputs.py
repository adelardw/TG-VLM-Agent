from pydantic import BaseModel, Field
from typing import Literal

class CalendarStructuredOutput(BaseModel):

    summary: str = Field(description="Название события")
    start: str = Field(description="Дата и время начала события в формате ISO 8601 %Y-%m-%dT%H:%M:%S")
    end: str = Field(description="Дата и время начала окончания события в формате ISO 8601 %Y-%m-%dT%H:%M:%S")
    description: str = Field(description="Описание события")
    location: str = Field('Moscow', description="Местоположение события, локация")
    timezone: str = Field('Europe/Moscow', description="Название временной зоны в формате IANA Time Zone Database")
    remind_format: Literal['hours', 'days', 'weeks', 'minutes'] = Field("minutes",description="Формат повторения. Возможные значения 'hours', 'days', 'weeks', 'minutes'")
    remind_num: int = Field(1,description="Единица времени. За сколько часов (hours), или  дней (days), или недель (weeks), или минут (minutes) нужно прислать напоминание о предстоящем событии.")
    remind_method: Literal['popup', 'email'] = Field('popup',description="Тип напоминания popup - увемдомление на телефон, email - на почту.")
    recurrence: list[str] = Field(description="Правила повторения события в формате iCalendar (RFC 5545)."\
                                  "Например ['RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=5'] (повторять 5 раз каждую неделю по понедельникам, средам и пятницам).")
